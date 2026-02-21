#!/usr/bin/env perl

package main;

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

# Parse CGI params
zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => "TITLE_ADV_DATASETS");

# Ensure root privileges
eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('datasets'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'datasets'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'list';
$action = '' unless defined $action;
$action =~ s/\0.*$//s;
$action =~ s/[&;].*$//;
$action =~ s/^\s+|\s+$//g;
$action = 'list' if $action eq '';
my $dataset = $in{'dataset'} || '';
$dataset =~ s/^\s+|\s+$//g;
my $pool_filter = $in{'pool'} || '';
$pool_filter =~ s/^\s+|\s+$//g;
$pool_filter = '' if $pool_filter ne '' && !is_pool_name($pool_filter);

# Plain anchor tabs for reliable switching (works with &ReadParse)
my @tabs_list = (
    [ 'list', 'TAB_DATASETS' ],
    [ 'create_fs', 'Create Filesystem' ],
    [ 'create_vol', 'Create Volume' ],
);

my $active_tab = $action;
$active_tab = 'create_fs' if $active_tab eq 'create';
$active_tab = 'list' if $active_tab ne 'list' && $active_tab ne 'create_fs' && $active_tab ne 'create_vol';

my $tabs_script = 'advanced_datasets.cgi';
if ($dataset ne '' &&
    is_dataset_name($dataset) &&
    ($action eq 'view' || $action eq 'create' || $action eq 'create_fs' || $action eq 'create_vol' ||
     $action eq 'snapshots' || $action eq 'quotas' || $action eq 'rename' || $action eq 'properties')) {
    $tabs_script .= '?dataset=' . &url_encode($dataset);
}

print zfsguru_print_tabs(
    script => $tabs_script,
    active => $active_tab,
    tabs   => \@tabs_list,
);

if ($action eq 'list' || !$action) {
    &action_list();
} elsif ($action eq 'view') {
    &action_view();
} elsif ($action eq 'create' || $action eq 'create_fs') {
    &action_create('filesystem');
} elsif ($action eq 'create_vol') {
    &action_create('volume');
} elsif ($action eq 'delete') {
    &action_delete();
} elsif ($action eq 'snapshots') {
    &action_snapshots();
} elsif ($action eq 'clone') {
    &action_clone();
} elsif ($action eq 'rollback') {
    &action_rollback();
} elsif ($action eq 'quotas') {
    &action_quotas();
} elsif ($action eq 'properties') {
    &action_properties();
} elsif ($action eq 'rename') {
    &action_rename();
} else {
    &action_list();
}

my $back_url = 'index.cgi';
if ($action ne 'list') {
    $back_url = 'advanced_datasets.cgi?action=list';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

# Action handlers

sub action_list {
    my $datasets = zfs_list([qw(name type used avail refer mountpoint)], '-t', 'filesystem,volume');
    my %pools_seen;
    for my $ds (@$datasets) {
        my $n = $ds->{name} || '';
        next unless length $n;
        my ($pool_root) = split('/', $n, 2);
        next unless defined $pool_root && length $pool_root;
        $pools_seen{$pool_root} = 1;
    }
    my @pool_opts = map { [ $_, $_ ] } sort keys %pools_seen;
    unshift @pool_opts, [ '', L("VALUE_ALL_POOLS") ];

    print &ui_form_start("advanced_datasets.cgi", "get");
    print &ui_hidden("action", "list");
    print &ui_table_start(L("TABLE_DATASET_FILTER"), "width=100%", 2);
    print &ui_table_row(L("COL_POOL"), &ui_select("pool", $pool_filter, \@pool_opts));
    print &ui_table_end();
    print &ui_form_end([ [ "apply_filter", L("BTN_APPLY_FILTER") ] ]);

    if ($pool_filter ne '') {
        my $clear_url = "advanced_datasets.cgi?action=list";
        print "<div class='zfsguru-warn-block'>";
        print "<b>" . L("COL_POOL") . ":</b> " . &html_escape($pool_filter) . " ";
        print "<a href='" . &html_escape($clear_url) . "'>" . &html_escape(L("BTN_CANCEL")) . "</a>";
        print "</div>";
    }

    my @heads = (
        L("COL_NAME"),
        L("COL_TYPE"),
        L("COL_USED"),
        L("COL_AVAILABLE"),
        L("COL_MOUNT_POINT"),
        L("COL_ACTIONS"),
    );

    my @data;
    for my $ds (@$datasets) {
        my $name = $ds->{name} || '';
        next unless length $name;
        if ($pool_filter ne '') {
            next if $name ne $pool_filter && index($name, $pool_filter.'/') != 0;
        }

        my $view_url = "advanced_datasets.cgi?action=view&dataset=" . &url_encode($name);
        my $name_link = &ui_link($view_url, &html_escape($name), "zfsguru-link");
        my $dtype = lc($ds->{type} || 'filesystem');
        my $dtype_label = $dtype eq 'volume' ? 'volume' : 'filesystem';

        my $mp = $ds->{mountpoint} || '-';
        my $mp_disp = &html_escape($mp);
        if ($mp eq '-' || $mp eq 'legacy') {
            $mp_disp = "<i>" . &html_escape($mp) . "</i>";
        } elsif ($mp =~ m{^/}) {
            $mp_disp = "<a href='files.cgi?action=browse&path=" . &url_encode($mp) . "'>" .
                       &html_escape($mp) . "</a>";
        }

        my @btns = (
            &ui_link_icon($view_url, L("BTN_DETAILS"), undef, { class => 'default' }),
            &ui_link_icon("advanced_datasets.cgi?action=snapshots&dataset=" . &url_encode($name), L("BTN_SNAPSHOTS"), undef, { class => 'default' }),
            &ui_link_icon("advanced_datasets.cgi?action=properties&dataset=" . &url_encode($name), L("BTN_PROPERTIES"), undef, { class => 'default' }),
            &ui_link_icon("advanced_datasets.cgi?action=rename&dataset=" . &url_encode($name), L("BTN_RENAME"), undef, { class => 'default' }),
            &ui_link_icon("advanced_datasets.cgi?action=delete&dataset=" . &url_encode($name), L("BTN_DELETE_DATASET"), undef, { class => 'danger' }),
        );
        if ($dtype ne 'volume') {
            splice @btns, 2, 0, &ui_link_icon("advanced_datasets.cgi?action=quotas&dataset=" . &url_encode($name), L("BTN_QUOTAS"), undef, { class => 'default' });
        }
        my $actions = "<div class='zfsguru-actionlinks'>" . join(" ", @btns) . "</div>";

        push @data, [
            $name_link,
            &html_escape($dtype_label),
            &html_escape($ds->{used} || '-'),
            &html_escape($ds->{avail} || '-'),
            $mp_disp,
            $actions,
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1,
        L("TABLE_DATASETS"), L("ERR_NO_DATASETS_FOUND"));
}

sub action_view {
    my $dataset_name = $in{'dataset'} || '';
    if (!is_dataset_name($dataset_name)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
        return;
    }
    
    my $datasets = zfs_list([qw(name type used avail refer mountpoint)], '-t', 'filesystem,volume');
    my $ds_info;
    for my $ds (@$datasets) {
        if ($ds->{name} eq $dataset_name) {
            $ds_info = $ds;
            last;
        }
    }
    
    if (!$ds_info) {
        print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
        return;
    }
    
    print &ui_subheading(L("SUB_DATASET", $dataset_name));
    print &ui_table_start(L("TABLE_DATASET_INFO"), "width=100%", 2);
    print &ui_table_row(L("COL_NAME"), &html_escape($ds_info->{name} || '-'));
    print &ui_table_row(L("COL_TYPE"), &html_escape($ds_info->{type} || 'filesystem'));
    print &ui_table_row(L("COL_USED"), &html_escape($ds_info->{used} || '-'));
    print &ui_table_row(L("COL_AVAILABLE"), &html_escape($ds_info->{avail} || '-'));
    print &ui_table_row(L("ROW_REFERENCED"), &html_escape($ds_info->{refer} || '-'));
    print &ui_table_row(L("COL_MOUNT_POINT"), &html_escape($ds_info->{mountpoint} || '-'));
    print &ui_table_end();
    
    # Show snapshots for this dataset
    my $snapshots = zfs_list_snapshots($dataset_name);
    if (@$snapshots) {
        print &ui_subheading(L("SUB_SNAPSHOTS"));
        my @heads = (
            L("COL_NAME"),
            L("COL_USED"),
            L("COL_CREATION_DATE"),
            L("COL_ACTIONS"),
        );
        my @data;
        for my $snap (@$snapshots) {
            my $full = $snap->{name} || '';
            next unless length $full;
            my $disp = $full;
            $disp =~ s/^\Q$dataset_name\E\@//;
            my @btns = (
                &ui_link_icon("advanced_datasets.cgi?action=rollback&snapshot=" . &url_encode($full), L("BTN_ROLLBACK"), undef, { class => 'warning' }),
                &ui_link_icon("advanced_datasets.cgi?action=clone&snapshot=" . &url_encode($full), L("BTN_CLONE"), undef, { class => 'default' }),
                &ui_link_icon("advanced_datasets.cgi?action=delete&snapshot=" . &url_encode($full), L("BTN_DELETE"), undef, { class => 'danger' }),
            );
            my $actions = "<div class='zfsguru-actionlinks'>" . join(" ", @btns) . "</div>";
            push @data, [
                &html_escape($disp),
                &html_escape($snap->{used} || '-'),
                &html_escape($snap->{creation} || '-'),
                $actions,
            ];
        }
        print &ui_columns_table(\@heads, 100, \@data, undef, 1,
            L("TABLE_SNAPSHOTS"), L("ERR_NO_SNAPSHOTS_FOUND"));
    }
}

sub apply_fd_acl_flags_to_mountpoint {
    my ($mp) = @_;
    return (0, 'Mountpoint is empty') unless defined $mp && $mp ne '' && $mp ne '-' && $mp ne 'none';
    return (0, 'Missing ACL tools') unless command_exists('getfacl') && command_exists('setfacl');

    my ($grc, $gout, $gerr) = run_cmd('getfacl', $mp);
    return (0, $gerr || 'getfacl failed') if $grc != 0 || !defined($gout) || $gout !~ /\S/;

    my ($owner_perm, $group_perm, $every_perm) = ('', '', '');
    for my $ln (split /\n/, $gout) {
        $owner_perm = $1 if !$owner_perm && $ln =~ /^\s*owner\@:(.*?):allow\s*$/;
        $group_perm = $1 if !$group_perm && $ln =~ /^\s*group\@:(.*?):allow\s*$/;
        $every_perm = $1 if !$every_perm && $ln =~ /^\s*everyone\@:(.*?):allow\s*$/;
    }
    return (0, 'Missing owner@/group@/everyone@ ACL entries')
        unless $owner_perm ne '' && $group_perm ne '' && $every_perm ne '';

    my @mods = (
        "owner\@:$owner_perm:fd-----:allow",
        "group\@:$group_perm:fd-----:allow",
        "everyone\@:$every_perm:fd-----:allow",
    );
    my ($src, $sout, $serr) = run_cmd('setfacl', '-m', $mods[0], '-m', $mods[1], '-m', $mods[2], $mp);
    return (0, $serr || 'setfacl failed') if $src != 0;
    return (1, '');
}

sub apply_fd_acl_flags_for_dataset {
    my ($ds) = @_;
    return (0, 'Invalid dataset') unless defined $ds && is_dataset_name($ds);
    my $acltype = zfs_get_prop_value($ds, 'acltype') // '';
    my $mp = zfs_get_prop_value($ds, 'mountpoint') // '';
    return (0, 'ACL type is not nfsv4') unless lc($acltype) eq 'nfsv4';
    return apply_fd_acl_flags_to_mountpoint($mp);
}

sub action_create {
    my ($mode) = @_;
    $mode = 'filesystem' if !defined($mode) || ($mode ne 'filesystem' && $mode ne 'volume');
    my $is_volume = ($mode eq 'volume') ? 1 : 0;
    my $action_name = $is_volume ? 'create_vol' : 'create_fs';

    my $datasets = zfs_list([qw(name)], '-t', 'filesystem');
    my %parent_seen;
    my @parent_opts;
    for my $ds (@$datasets) {
        my $n = $ds->{name} || '';
        next unless length $n;
        if (!$parent_seen{$n}++) {
            push @parent_opts, [ $n, $n ];
        }
        my ($pool) = split('/', $n, 2);
        if (defined $pool && length $pool && !$parent_seen{$pool}++) {
            push @parent_opts, [ $pool, $pool ];
        }
    }
    @parent_opts = sort { $a->[0] cmp $b->[0] } @parent_opts;
    unshift @parent_opts, [ '', '-- Select parent dataset/filesystem --' ];

    my $seed_dataset = '';
    if (defined $in{'dataset'} && $in{'dataset'} ne '') {
        my $cand = $in{'dataset'};
        $cand =~ s/^\s+|\s+$//g;
        if (is_dataset_name($cand) && $parent_seen{$cand}) {
            $seed_dataset = $cand;
        }
    }

    my %seed_props;
    if ($seed_dataset ne '') {
        for my $prop (qw(
            compression sync atime recordsize exec canmount
            acltype aclinherit aclmode xattr
            volblocksize logbias primarycache secondarycache refreservation
        )) {
            my $v = zfs_get_prop_value($seed_dataset, $prop);
            next unless defined $v;
            $v =~ s/^\s+|\s+$//g;
            next if $v eq '' || $v eq '-';
            if ($prop =~ /^(?:compression|sync|atime|exec|canmount|acltype|aclinherit|aclmode|xattr|logbias|primarycache|secondarycache)$/) {
                $v = lc($v);
            }
            if ($prop eq 'compression') {
                $v = 'zstd' if $v =~ /^zstd/;
                $v = 'gzip' if $v =~ /^gzip/;
                $v = 'lz4' if $v eq 'on';
            }
            $seed_props{$prop} = $v;
        }
    }

    my $select_default = sub {
        my ($in_key, $seed_key, $fallback, $allowed_ref) = @_;
        my $v;
        if (exists $in{$in_key}) {
            $v = defined($in{$in_key}) ? $in{$in_key} : '';
        } elsif ($seed_key && exists $seed_props{$seed_key}) {
            $v = $seed_props{$seed_key};
        } else {
            $v = $fallback;
        }
        if ($allowed_ref && ref($allowed_ref) eq 'ARRAY') {
            my %ok = map { $_ => 1 } @$allowed_ref;
            $v = $fallback if !exists $ok{$v};
        }
        return $v;
    };

    if ($in{'do_create'}) {
        my $name = '';
        my $parent = $in{'parent_dataset'} // '';
        my $child = $in{'child_name'} // '';
        my $mountpoint = $in{'mountpoint'} // '';
        my $mountpoint_user_changed = (defined $in{'mountpoint_user_changed'} && $in{'mountpoint_user_changed'} =~ /^(?:1|on|yes|true)$/i) ? 1 : 0;
        $parent =~ s/^\s+|\s+$//g;
        $child =~ s/^\s+|\s+$//g;
        $mountpoint =~ s/^\s+|\s+$//g;

        if ($parent ne '' && $child ne '') {
            $name = "$parent/$child";
        } else {
            print &ui_print_error("Please select a parent dataset/filesystem and enter a name.");
            return;
        }

        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
            return;
        }

        my $compression = $in{'compression'} || ($is_volume ? 'lz4' : 'off');
        my %allowed_comp = map { $_ => 1 } qw(off lz4 gzip lzjb zstd);
        if (!$allowed_comp{$compression}) {
            print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "compression", $compression));
            return;
        }

        if ($is_volume) {
            my $volsize = $in{'volsize'} // '';
            $volsize =~ s/^\s+|\s+$//g;
            if ($volsize eq '' || !is_zfs_size($volsize) || $volsize =~ /^(none|auto)$/i) {
                print &ui_print_error(L("ERR_VOLUME_SIZE_INVALID", $volsize || '(empty)'));
                return;
            }

            my $sync = $in{'sync'} || 'standard';
            my $volblocksize = $in{'volblocksize'} || '16K';
            my $logbias = $in{'logbias'} || 'latency';
            my $primarycache = $in{'primarycache'} || 'all';
            my $secondarycache = $in{'secondarycache'} || 'all';
            my $refreservation = $in{'refreservation'} // '';
            $refreservation =~ s/^\s+|\s+$//g;
            my $sparse = $in{'sparse'} ? 1 : 0;

            if ($sync !~ /^(standard|always|disabled)$/) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "sync", $sync));
                return;
            }
            if ($volblocksize !~ /^(default|512|1K|2K|4K|8K|16K|32K|64K|128K)$/) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "volblocksize", $volblocksize));
                return;
            }
            if ($logbias !~ /^(latency|throughput)$/) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "logbias", $logbias));
                return;
            }
            if ($primarycache !~ /^(default|all|none|metadata)$/) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "primarycache", $primarycache));
                return;
            }
            if ($secondarycache !~ /^(default|all|none|metadata)$/) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "secondarycache", $secondarycache));
                return;
            }
            if ($refreservation ne '' && $refreservation ne 'none' && !is_zfs_size($refreservation)) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "refreservation", $refreservation));
                return;
            }

            my @opts;
            push @opts, ('-s') if $sparse;
            push @opts, ('-o', "compression=$compression");
            push @opts, ('-o', "sync=$sync");
            push @opts, ('-o', "volblocksize=$volblocksize") if $volblocksize ne 'default';
            push @opts, ('-o', "logbias=$logbias");
            push @opts, ('-o', "primarycache=$primarycache") if $primarycache ne 'default';
            push @opts, ('-o', "secondarycache=$secondarycache") if $secondarycache ne 'default';
            if ($refreservation ne '') {
                push @opts, ('-o', "refreservation=$refreservation");
            } elsif ($sparse) {
                push @opts, ('-o', "refreservation=none");
            }

            eval {
                zfs_create_volume($name, $volsize, @opts);
                log_info("Created volume: $name (size=$volsize)");
                print &ui_print_success(L("SUCCESS_VOLUME_CREATED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_VOLUME_CREATE_FAILED", $@));
            }
            return;
        }

        my $atime = $in{'atime'} || 'on';
        my $acltype = $in{'acltype'} || 'nfsv4';
        my $aclinherit = $in{'aclinherit'} || 'passthrough';
        my $aclmode = $in{'aclmode'} || 'passthrough';
        my $xattr = $in{'xattr'} || 'sa';
        my $recordsize = $in{'recordsize'} || '128K';
        my $sync = $in{'sync'} || 'standard';
        my $exec = $in{'exec'} || 'on';
        my $canmount = $in{'canmount'} || 'on';

        if ($mountpoint_user_changed && $mountpoint && $mountpoint ne 'none' && $mountpoint ne 'legacy' && !is_mountpoint($mountpoint)) {
            print &ui_print_error(L("ERR_MOUNTPOINT_INVALID", $mountpoint));
            return;
        }
        if ($atime !~ /^(on|off)$/) {
            print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "atime", $atime));
            return;
        }

        my $props = {
            compression => $compression,
            atime => $atime,
            acltype => $acltype,
            aclinherit => $aclinherit,
            aclmode => $aclmode,
            xattr => $xattr,
            recordsize => $recordsize,
            sync => $sync,
            exec => $exec,
            canmount => $canmount,
        };
        $props->{mountpoint} = $mountpoint if $mountpoint_user_changed && $mountpoint ne '';

        eval {
            my @opts;
            for my $k (sort keys %{$props}) {
                my $v = $props->{$k};
                next unless defined $v;
                push @opts, ('-o', "$k=$v");
            }
            zfs_create($name, @opts);
            if ($in{'acl_inherit_fd'}) {
                my ($ok_fd, $msg_fd) = apply_fd_acl_flags_for_dataset($name);
                if (!$ok_fd) {
                    log_warn("Dataset created but ACL :fd flag apply skipped/failed for $name: $msg_fd");
                } else {
                    log_info("Applied ACL :fd inheritance flags for dataset $name");
                }
            }
            log_info("Created dataset: $name");
            print &ui_print_success(L("SUCCESS_DATASET_CREATED", $name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DATASET_CREATE_FAILED", $@));
        }
        return;
    }

    my $parent_default = exists $in{'parent_dataset'} ? ($in{'parent_dataset'} // '') : $seed_dataset;
    $parent_default = '' if $parent_default ne '' && !$parent_seen{$parent_default};
    my $child_default = $in{'child_name'} // '';
    my $mountpoint_user_changed_default =
        (defined $in{'mountpoint_user_changed'} && $in{'mountpoint_user_changed'} =~ /^(?:1|on|yes|true)$/i) ? 1 : 0;

    my %parent_mount_map;
    for my $opt (@parent_opts) {
        next unless ref($opt) eq 'ARRAY';
        my $pn = $opt->[0] // '';
        next if $pn eq '' || !$parent_seen{$pn};
        next unless is_dataset_name($pn);
        my $pm = zfs_get_prop_value($pn, 'mountpoint');
        next unless defined $pm;
        $pm =~ s/^\s+|\s+$//g;
        next unless $pm =~ m{^/};
        $parent_mount_map{$pn} = $pm;
    }

    my $mountpoint_default = '';
    if (exists $in{'mountpoint'}) {
        $mountpoint_default = $in{'mountpoint'} // '';
    } elsif ($parent_default ne '' && exists $parent_mount_map{$parent_default}) {
        my $base = $parent_mount_map{$parent_default};
        $base =~ s{/+$}{};
        my $child_part = $child_default // '';
        $child_part =~ s{^/+|/+$}{}g;
        $mountpoint_default = $child_part ne '' ? "$base/$child_part" : $base;
    }

    my $compression_default = $select_default->(
        'compression', 'compression', ($is_volume ? 'lz4' : 'off'),
        [qw(off lz4 zstd gzip lzjb)]
    );
    my $sync_default = $select_default->(
        'sync', 'sync', 'standard',
        [qw(standard always disabled)]
    );
    my $volblocksize_default = $select_default->(
        'volblocksize', 'volblocksize', '16K',
        [qw(default 512 1K 2K 4K 8K 16K 32K 64K 128K)]
    );
    my $logbias_default = $select_default->(
        'logbias', 'logbias', 'latency',
        [qw(latency throughput)]
    );
    my $primarycache_default = $select_default->(
        'primarycache', 'primarycache', 'all',
        [qw(default all none metadata)]
    );
    my $secondarycache_default = $select_default->(
        'secondarycache', 'secondarycache', 'all',
        [qw(default all none metadata)]
    );
    my $refreservation_default = exists $in{'refreservation'}
        ? ($in{'refreservation'} // '')
        : (exists($seed_props{refreservation}) ? $seed_props{refreservation} : '');
    my $atime_default = $select_default->(
        'atime', 'atime', 'on',
        [qw(on off)]
    );
    my $recordsize_default = $select_default->(
        'recordsize', 'recordsize', '128K',
        [qw(512 1K 2K 4K 8K 16K 32K 64K 128K 256K 512K 1M 2M 4M)]
    );
    my $exec_default = $select_default->(
        'exec', 'exec', 'on',
        [qw(on off)]
    );
    my $canmount_default = $select_default->(
        'canmount', 'canmount', 'on',
        [qw(on off noauto)]
    );
    my $acltype_default = $select_default->(
        'acltype', 'acltype', 'nfsv4',
        [qw(nfsv4 posix off)]
    );
    my $aclinherit_default = $select_default->(
        'aclinherit', 'aclinherit', 'passthrough',
        [qw(passthrough passthrough-x restricted noallow discard)]
    );
    my $aclmode_default = $select_default->(
        'aclmode', 'aclmode', 'passthrough',
        [qw(passthrough restricted groupmask discard)]
    );
    my $xattr_default = $select_default->(
        'xattr', 'xattr', 'sa',
        [qw(sa on off)]
    );

    if ($is_volume) {
        print &ui_subheading("Create New Volume");
        print &ui_form_start("advanced_datasets.cgi", "post");
        print &ui_hidden("action", $action_name);
        print &ui_hidden("dataset", $seed_dataset) if $seed_dataset ne '';
        print &ui_hidden("do_create", 1);
        print &ui_table_start("Volume Configuration", "width=100%", 2);
        print &ui_table_row("Parent Dataset / Filesystem", &ui_select("parent_dataset", $parent_default, \@parent_opts));
        print &ui_table_row("Volume Name", &ui_textbox("child_name", $child_default, 30) .
            "<br><small>Use short name only (without slash)</small>");
        print &ui_table_row("Volume Size", &ui_textbox("volsize", ($in{'volsize'} || ''), 20) .
            "<br><small>" . L("HINT_VOLUME_SIZE") . "</small>");
        print &ui_table_row("Compression", &ui_select("compression", $compression_default, [
            [ "off", L("OPT_OFF") ],
            [ "lz4", L("OPT_ON_LZ4") ],
            [ "zstd", "ZSTD" ],
            [ "gzip", "GZIP" ],
            [ "lzjb", "LZJB" ],
        ]));
        print &ui_table_row("Sync", &ui_select("sync", $sync_default, [
            [ "standard", "standard (default)" ],
            [ "always", "always" ],
            [ "disabled", "disabled (performance, data loss risk)" ],
        ]));
        print &ui_table_row("Volume Block Size", &ui_select("volblocksize", $volblocksize_default, [
            [ "default", "default" ],
            [ "512", "(512B)" ], [ "1K", "(1K)" ], [ "2K", "(2K)" ],
            [ "4K", "(4K) Swap" ], [ "8K", "(8K) Databases" ],
            [ "16K", "16K (VM/Default)" ], [ "32K", "32K" ],
            [ "64K", "64K (Backups)" ], [ "128K", "128K" ],
        ]));
        print &ui_table_row("Log Bias", &ui_select("logbias", $logbias_default, [
            [ "latency", "latency (databases, sync-heavy)" ],
            [ "throughput", "throughput (streaming)" ],
        ]));
        print &ui_table_row("Primary Cache", &ui_select("primarycache", $primarycache_default, [
            [ "default", "default" ],
            [ "all", "all (filesystems)" ],
            [ "none", "none (swap)" ],
            [ "metadata", "metadata (VM, iSCSI)" ],
        ]));
        print &ui_table_row("Secondary Cache", &ui_select("secondarycache", $secondarycache_default, [
            [ "default", "default" ],
            [ "all", "all (general filesystems)" ],
            [ "none", "none (media)" ],
            [ "metadata", "metadata (VM, databases)" ],
        ]));
        my $sparse_default = defined $in{'sparse'} ? ($in{'sparse'} ? 1 : 0) : 1;
        print &ui_table_row("Sparse Volume", &ui_checkbox("sparse", 1, "Create as sparse volume (default)", $sparse_default) .
            "<br><small id='thick_note'>(Volume is thick provisioned)</small>");
        print &ui_table_row("Refreservation", &ui_textbox("refreservation", $refreservation_default, 20) .
            "<br><small id='refreservation_hint'>default: none</small>");
        print &ui_table_end();
        print "<script>
(function(){
  var sizeEl = document.getElementsByName('volsize')[0];
  var sparseEl = document.getElementsByName('sparse')[0];
  var hintEl = document.getElementById('refreservation_hint');
  var thickEl = document.getElementById('thick_note');
  function updateHints(){
    if (hintEl && sizeEl) {
      var v = (sizeEl.value || '').trim();
      hintEl.textContent = v ? ('maximum Size: ' + v + ' default: none') : 'default: none';
    }
    if (thickEl && sparseEl) {
      thickEl.style.display = sparseEl.checked ? 'none' : 'inline';
    }
  }
  if (sizeEl) sizeEl.addEventListener('input', updateHints);
  if (sparseEl) sparseEl.addEventListener('change', updateHints);
  updateHints();
})();
</script>";
        print &ui_form_end([ [ "do_create", "Create Volume" ] ]);
        return;
    }

    my $acltype_create_default = $acltype_default;
    my $acl_fd_create_default = defined $in{'acl_inherit_fd'}
        ? ($in{'acl_inherit_fd'} ? 1 : 0)
        : (lc($acltype_create_default) eq 'nfsv4' ? 1 : 0);

    print &ui_subheading("Create New Filesystem");
    print &ui_form_start("advanced_datasets.cgi", "post");
    print &ui_hidden("action", $action_name);
    print &ui_hidden("dataset", $seed_dataset) if $seed_dataset ne '';
    print &ui_hidden("do_create", 1);
    print &ui_hidden("mountpoint_user_changed", ($mountpoint_user_changed_default ? 1 : 0));

    print &ui_table_start(L("TABLE_DATASET_CONFIG"), "width=100%", 2);
    print &ui_table_row("Parent Dataset / Filesystem", &ui_select("parent_dataset", $parent_default, \@parent_opts));
    print &ui_table_row("Filesystem Name", &ui_textbox("child_name", $child_default, 30) .
        "<br><small>Use short name only (without slash)</small>");
    print &ui_table_row(L("COL_MOUNT_POINT"), &ui_filebox("mountpoint", $mountpoint_default, 40, 0, undef, undef, 1) .
        "<br><small>" . L("HINT_MOUNTPOINT_DEFAULT") . "</small>");
    print &ui_table_row(L("ROW_COMPRESSION"), &ui_select("compression", $compression_default, [
        [ "off", L("OPT_OFF") ],
        [ "lz4", L("OPT_ON_LZ4") ],
        [ "zstd", "ZSTD" ],
        [ "gzip", "GZIP" ],
        [ "lzjb", "LZJB" ],
    ]));
    print &ui_table_row(L("ROW_ATIME"), &ui_select("atime", $atime_default, [
        [ "on", L("OPT_ENABLED") ],
        [ "off", L("OPT_DISABLED") ],
    ]));
    print &ui_table_row(L("ROW_RECORDSIZE"), &ui_select("recordsize", $recordsize_default, [
        [ "512", "512B" ], [ "1K", "1K" ], [ "2K", "2K" ], [ "4K", "4K" ],
        [ "8K", "8K" ], [ "16K", "16K" ], [ "32K", "32K" ], [ "64K", "64K" ],
        [ "128K", "128K (General default)" ], [ "256K", "256K" ], [ "512K", "512K" ],
        [ "1M", "1M (Media/Large file default)" ], [ "2M", "2M" ], [ "4M", "4M" ],
    ]));
    print &ui_table_row(L("ROW_SYNC_BEHAVIOR"), &ui_select("sync", $sync_default, [
        [ "standard", "standard (default)" ],
        [ "always", "always" ],
        [ "disabled", "disabled (performance, data loss risk)" ],
    ]));
    print &ui_table_row("Exec", &ui_select("exec", $exec_default, [
        [ "on", "on" ],
        [ "off", "off" ],
    ]));
    print &ui_table_row("Canmount", &ui_select("canmount", $canmount_default, [
        [ "on", "on" ],
        [ "off", "off" ],
        [ "noauto", "noauto" ],
    ]));
    print &ui_table_row("ACL type", &ui_select("acltype", $acltype_default, [
        [ "nfsv4", "nfsv4" ],
        [ "posix", "posix" ],
        [ "off", "off" ],
    ]));
    print &ui_table_row("ACL inherit", &ui_select("aclinherit", $aclinherit_default, [
        [ "passthrough", "passthrough" ],
        [ "passthrough-x", "passthrough-x" ],
        [ "restricted", "restricted" ],
        [ "noallow", "noallow" ],
        [ "discard", "discard" ],
    ]));
    print &ui_table_row("ACL mode", &ui_select("aclmode", $aclmode_default, [
        [ "passthrough", "passthrough" ],
        [ "restricted", "restricted" ],
        [ "groupmask", "groupmask" ],
        [ "discard", "discard" ],
    ]));
    print &ui_table_row("xattr", &ui_select("xattr", $xattr_default, [
        [ "sa", "sa" ],
        [ "on", "on" ],
        [ "off", "off" ],
    ]));
    print &ui_table_row("ACL inherit flags", &ui_checkbox("acl_inherit_fd", 1, "Add :fd to base NFSv4 ACL entries", $acl_fd_create_default));
    print &ui_table_end();

    my $jsq = sub {
        my ($s) = @_;
        $s = '' unless defined $s;
        $s =~ s/\\/\\\\/g;
        $s =~ s/'/\\'/g;
        $s =~ s/\r//g;
        $s =~ s/\n/\\n/g;
        return $s;
    };
    my @mp_map_js;
    for my $k (sort keys %parent_mount_map) {
        push @mp_map_js, "        '" . $jsq->($k) . "': '" . $jsq->($parent_mount_map{$k}) . "'";
    }
    my $mp_map_js = @mp_map_js ? join(",\n", @mp_map_js) : "";
    print "<script>
(function(){
    var parentEl = document.getElementsByName('parent_dataset')[0];
    var childEl = document.getElementsByName('child_name')[0];
    var mountEl = document.getElementsByName('mountpoint')[0];
    var changedEl = document.getElementsByName('mountpoint_user_changed')[0];
    if (!parentEl || !childEl || !mountEl || !changedEl) return;
    var parentMountMap = {
$mp_map_js
    };
    function joinMount(base, child) {
        if (!base || base.charAt(0) !== '/') return '';
        base = base.replace(/\\/+$/g, '');
        child = (child || '').replace(/^\\/+|\\/+$/g, '');
        return child ? (base + '/' + child) : base;
    }
    function autoFillMountpoint() {
        if (changedEl.value === '1') return;
        var parent = parentEl.value || '';
        var base = parentMountMap[parent] || '';
        mountEl.value = joinMount(base, childEl.value || '');
    }
    function markChanged() {
        changedEl.value = '1';
    }
    mountEl.addEventListener('input', markChanged);
    mountEl.addEventListener('change', markChanged);
    parentEl.addEventListener('change', autoFillMountpoint);
    childEl.addEventListener('input', autoFillMountpoint);
    childEl.addEventListener('change', autoFillMountpoint);
    autoFillMountpoint();
})();
</script>";

    print &ui_form_end([ [ "do_create", "Create Filesystem" ] ]);
}

sub action_delete {
    my $dataset_name = $in{'dataset'} || '';
    my $snapshot_name = $in{'snapshot'} || '';
    
    if ($dataset_name) {
        if (!is_dataset_name($dataset_name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
            return;
        }

        my @swap_active;
        my $swap_disp = '';
        eval {
            # Detect active swap volumes under this dataset so we can disable swap
            # before destroy (destroying an active swap zvol is dangerous).
            my $vols = zfs_list([qw(name)], '-t', 'volume', '-r', $dataset_name);
            for my $v (@$vols) {
                my $vn = $v->{name} || '';
                next unless length $vn;
                my $swap = zfs_get_prop_value($vn, 'org.freebsd:swap');
                next unless defined $swap && $swap eq 'on';
                push @swap_active, $vn if swap_is_active($vn);
            }
        };
        if (@swap_active) {
            my $max = 5;
            $swap_disp = (@swap_active > $max)
                ? join(', ', @swap_active[0 .. ($max - 1)]) . " ..."
                : join(', ', @swap_active);
        }

        my @dependent_clones;
        my $clones_disp = '';
        eval {
            # Detect dependent clones (snapshots with non-empty "clones" property).
            # If present, plain "zfs destroy -r" will fail and the user may want "-R".
            my ($rc, $out, $err) = run_cmd(
                $zfsguru_lib::ZFS, 'get', '-H', '-o', 'name,value',
                '-r', '-t', 'snapshot', 'clones', $dataset_name
            );
            if ($rc == 0 && $out) {
                my %seen;
                for my $line (split /\n/, $out) {
                    next unless length $line;
                    my (undef, $clones) = split /\t/, $line, 2;
                    next unless defined $clones && length $clones && $clones ne '-';
                    for my $c (split /,/, $clones) {
                        $c =~ s/^\s+|\s+$//g;
                        next unless length $c;
                        next if $seen{$c}++;
                        push @dependent_clones, $c;
                    }
                }
            }
        };
        if (@dependent_clones) {
            my $max = 5;
            $clones_disp = (@dependent_clones > $max)
                ? join(', ', @dependent_clones[0 .. ($max - 1)]) . " ..."
                : join(', ', @dependent_clones);
        }

        my $impact = zfs_list(
            [qw(name type used avail refer mountpoint)],
            '-r', $dataset_name, '-t', 'all'
        );

        if ($in{'do_delete'}) {
            my $destroy_dependents = $in{'destroy_dependents'} ? 1 : 0;

            if (!$in{'confirm_understand'}) {
                print &ui_print_error(L("ERR_CONFIRM_DESTROY_REQUIRED"));
                print &ui_alert(L("MSG_DATASET_DESTROY_WARNING"), "danger");
                return;
            }
            if (@swap_active && !$in{'confirm_swap_off'}) {
                print &ui_print_error(L("ERR_CONFIRM_SWAP_OFF_REQUIRED"));
                print &ui_alert(L("MSG_DATASET_SWAP_ACTIVE", $swap_disp), "warning");
                return;
            }
            if ($destroy_dependents && !$in{'confirm_destroy_dependents'}) {
                print &ui_print_error(L("ERR_CONFIRM_DESTROY_DEPENDENTS_REQUIRED"));
                print &ui_alert(L("MSG_DESTROY_DEPENDENTS_WARNING"), "warning");
                return;
            }
            eval {
                if (@swap_active) {
                    for my $vol (@swap_active) {
                        next unless swap_is_active($vol);
                        swap_off($vol);
                        log_info("swapoff before dataset destroy: $vol (parent $dataset_name)");
                    }
                }
                my @destroy_opts = $destroy_dependents ? ('-R') : ('-r');
                zfs_destroy($dataset_name, @destroy_opts);
                log_info("Deleted dataset: $dataset_name");
                print &ui_print_success(L("SUCCESS_DATASET_DELETED"));
            };
            if ($@) {
                print &ui_print_error(L("ERR_DATASET_DELETE_FAILED", $@));
            }
            return;
        }
        
        print &ui_print_error_header(L("HDR_DELETE_DATASET"));
        print "<p>" . L("CONFIRM_DELETE_DATASET", &html_escape($dataset_name)) . "</p>";
        print &ui_alert(L("MSG_DATASET_DESTROY_WARNING"), "danger");
        print "<p>" . L("MSG_REVIEW_COMMAND") . "</p>";
        print "<div class='zfsguru-danger-block'>" . &html_escape("zfs destroy -r $dataset_name") . "</div>";
        if (@swap_active) {
            print &ui_alert(L("MSG_DATASET_SWAP_ACTIVE", $swap_disp), "warning");
        }
        if (@dependent_clones) {
            print &ui_alert(L("MSG_DATASET_DEPENDENT_CLONES", $clones_disp), "warning");
        }

        if ($impact && @$impact) {
            print &ui_subheading(L("SUB_DATASET_DESTROY_IMPACT"));
            my $fmt_mp = sub {
                my ($mp) = @_;
                $mp = '-' if !defined $mp || $mp eq '';
                if ($mp eq '-' || $mp eq 'legacy') {
                    return "<i>" . &html_escape($mp) . "</i>";
                }
                if ($mp =~ m{^/}) {
                    return "<a href='files.cgi?action=browse&path=" . &url_encode($mp) . "'>" .
                        &html_escape($mp) . "</a>";
                }
                return &html_escape($mp);
            };

            my @heads = (
                L("COL_NAME"),
                L("COL_TYPE"),
                L("COL_USED"),
                L("COL_AVAILABLE"),
                L("COL_REFERENCED"),
                L("COL_MOUNT_POINT"),
            );

            my @data;
            for my $r (@$impact) {
                my $n = $r->{name} || '';
                next unless length $n;
                push @data, [
                    &html_escape($n),
                    &html_escape($r->{type} || '-'),
                    &html_escape($r->{used} || '-'),
                    &html_escape($r->{avail} || '-'),
                    &html_escape($r->{refer} || '-'),
                    $fmt_mp->($r->{mountpoint}),
                ];
            }

            print &ui_columns_table(\@heads, 100, \@data, undef, 1,
                L("TABLE_DATASET_DESTROY_IMPACT"), L("ERR_NO_DATASETS_FOUND"));
        }

        print &ui_form_start("advanced_datasets.cgi", "post");
        print &ui_hidden("action", "delete");
        print &ui_hidden("dataset", $dataset_name);
        print &ui_table_start(L("TABLE_DESTROY_CONFIRM"), "width=100%", 2);
        print &ui_table_row(L("ROW_CONFIRM"),
            &ui_checkbox('confirm_understand', 1, L('LBL_CONFIRM_UNDERSTAND_DESTROY'), 0));
        if (@swap_active) {
            print &ui_table_row(L("ROW_CONFIRM_SWAP_OFF"),
                &ui_checkbox('confirm_swap_off', 1, L('LBL_CONFIRM_SWAP_OFF'), 0));
        }
        print &ui_table_row(L("ROW_DESTROY_DEPENDENTS"),
            &ui_checkbox('destroy_dependents', 1, L('LBL_DESTROY_DEPENDENTS'), 0) .
            "<br />" .
            &ui_checkbox('confirm_destroy_dependents', 1, L('LBL_CONFIRM_DESTROY_DEPENDENTS'), 0));
        print &ui_table_end();
        print &ui_submit(L("BTN_DELETE_DATASET"), "do_delete") . " ";
        print &ui_link("advanced_datasets.cgi?action=list", L("BTN_CANCEL"));
        print &ui_form_end();
    } elsif ($snapshot_name) {
        if (!is_snapshot_fullname($snapshot_name)) {
            print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
            return;
        }

        if ($in{'do_delete'}) {
            if (!$in{'confirm_snapshot_destroy'}) {
                print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_DESTROY_REQUIRED"));
                print &ui_alert(L("MSG_SNAPSHOT_DESTROY_WARNING"), "warning");
                return;
            }
            eval {
                zfs_destroy_snapshot($snapshot_name);
                log_info("Deleted snapshot: $snapshot_name");
                print &ui_print_success(L("SUCCESS_SNAPSHOT_DELETED"));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SNAPSHOT_DELETE_FAILED", $@));
            }
            return;
        }
        
        print &ui_print_error_header(L("HDR_DELETE_SNAPSHOT"));
        print "<p>" . L("CONFIRM_DELETE_SNAPSHOT", &html_escape($snapshot_name)) . "</p>";
        print &ui_alert(L("MSG_SNAPSHOT_DESTROY_WARNING"), "warning");
        print "<p>" . L("MSG_REVIEW_COMMAND") . "</p>";
        print "<div class='zfsguru-danger-block'>" . &html_escape("zfs destroy $snapshot_name") . "</div>";
        print &ui_form_start("advanced_datasets.cgi", "post");
        print &ui_hidden("action", "delete");
        print &ui_hidden("snapshot", $snapshot_name);
        print &ui_table_start(L("TABLE_DESTROY_CONFIRM"), "width=100%", 2);
        print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_DESTROY"),
            &ui_checkbox('confirm_snapshot_destroy', 1, L('LBL_CONFIRM_SNAPSHOT_DESTROY'), 0));
        print &ui_table_end();
        print &ui_submit(L("BTN_DELETE_SNAPSHOT"), "do_delete") . " ";

        my $ds = $snapshot_name;
        $ds =~ s/\@.*$//;
        my $back = is_dataset_name($ds)
            ? ("advanced_datasets.cgi?action=snapshots&dataset=" . &url_encode($ds))
            : "advanced_datasets.cgi?action=list";
        print &ui_link($back, L("BTN_CANCEL"));
        print &ui_form_end();
    }
}

sub action_snapshots {
    my $dataset_name = $in{'dataset'} || '';
    if (!is_dataset_name($dataset_name)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
        return;
    }
    
    if ($in{'create_snapshot'}) {
        my $snap_name = $in{'snapshot_name'} // '';
        $snap_name =~ s/^\s+|\s+$//g;
        if (!$snap_name || $snap_name =~ /\@/) {
            print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
            return;
        }
        eval {
            my $full_snapshot = "$dataset_name\@$snap_name";
            zfs_snapshot($full_snapshot);
            log_info("Created snapshot: $dataset_name\@$snap_name");
            print &ui_print_success(L("SUCCESS_SNAPSHOT_CREATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SNAPSHOT_CREATE_FAILED", $@));
        }
    }
    
    print &ui_subheading(L("SUB_SNAPSHOTS_FOR", $dataset_name));
    
    print &ui_form_start("advanced_datasets.cgi", "post");
    print &ui_hidden("action", "snapshots");
    print &ui_hidden("dataset", $dataset_name);
    print &ui_table_start(L("TABLE_CREATE_SNAPSHOT"), "width=100%", 2);
    print &ui_table_row(L("ROW_SNAPSHOT_NAME"), &ui_textbox("snapshot_name", "", 30) .
        "<br><small>" . L("HINT_SNAPSHOT_NAME") . "</small>");
    print &ui_table_end();
    print &ui_form_end([ [ "create_snapshot", L("BTN_CREATE_SNAPSHOT") ] ]);
    
    my $snapshots = zfs_list_snapshots($dataset_name);
    if (@$snapshots) {
        my @heads = (L("COL_SNAPSHOT"), L("COL_USED"), L("COL_CREATION"), L("COL_ACTIONS"));
        my @data;
        for my $snap (@$snapshots) {
            my $full = $snap->{name} || '';
            next unless length $full;
            my $disp = $full;
            $disp =~ s/^\Q$dataset_name\E\@//;
            my @btns = (
                &ui_link_icon("advanced_datasets.cgi?action=rollback&snapshot=" . &url_encode($full), L("BTN_ROLLBACK"), undef, { class => 'warning' }),
                &ui_link_icon("advanced_datasets.cgi?action=clone&snapshot=" . &url_encode($full), L("BTN_CLONE"), undef, { class => 'default' }),
                &ui_link_icon("advanced_datasets.cgi?action=delete&snapshot=" . &url_encode($full), L("BTN_DELETE"), undef, { class => 'danger' }),
            );
            my $actions = "<div class='zfsguru-actionlinks'>" . join(" ", @btns) . "</div>";
            push @data, [
                &html_escape($disp),
                &html_escape($snap->{used} || '-'),
                &html_escape($snap->{creation} || '-'),
                $actions,
            ];
        }
        print &ui_columns_table(\@heads, 100, \@data, undef, 1,
            L("TABLE_SNAPSHOTS"), L("ERR_NO_SNAPSHOTS_FOUND"));
    } else {
        print &ui_print_error(L("ERR_NO_SNAPSHOTS_FOUND"));
    }
}

sub action_clone {
    my $snapshot_name = $in{'snapshot'} || '';
    if ($snapshot_name && !is_snapshot_fullname($snapshot_name)) {
        print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
        return;
    }
    
    if ($in{'do_clone'}) {
        my $target = $in{'target_dataset'};
        if (!is_dataset_name($target)) {
            print &ui_print_error(L("ERR_CLONE_TARGET_INVALID", $target));
            return;
        }
        eval {
            zfs_clone($snapshot_name, $target);
            log_info("Cloned snapshot: $snapshot_name -> $target");
            print &ui_print_success(L("SUCCESS_SNAPSHOT_CLONED", $target));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SNAPSHOT_CLONE_FAILED", $@));
        }
        return;
    }
    
    if ($snapshot_name) {
        print &ui_subheading(L("SUB_CLONE_SNAPSHOT", $snapshot_name));
        print &ui_form_start("advanced_datasets.cgi", "post");
        print &ui_hidden("action", "clone");
        print &ui_hidden("snapshot", $snapshot_name);
        print &ui_hidden("do_clone", 1);
        
        print &ui_table_start(L("TABLE_CLONE_CONFIG"), "width=100%", 2);
        print &ui_table_row(L("ROW_TARGET_DATASET"), &ui_textbox("target_dataset", "", 40));
        print &ui_table_end();
        
        print &ui_form_end([ [ "do_clone", L("BTN_CLONE") ] ]);
    }
}

sub action_rollback {
    my $snapshot_name = $in{'snapshot'} || '';
    if (!is_snapshot_fullname($snapshot_name)) {
        print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
        return;
    }

    my ($dataset_name) = split(/\@/, $snapshot_name, 2);
    if (!is_dataset_name($dataset_name)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
        return;
    }

    my $back = "advanced_datasets.cgi?action=snapshots&dataset=" . &url_encode($dataset_name);
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back .= "&xnavigation=" . $in{'xnavigation'};
    }

    my %opt = (
        destroy_newer => ($in{'rollback_destroy_newer'} ? 1 : 0),
        destroy_clones => ($in{'rollback_destroy_clones'} ? 1 : 0),
        force => ($in{'rollback_force'} ? 1 : 0),
    );

    if ($in{'do_rollback'}) {
        if (!$in{'confirm_snapshot_rollback'}) {
            print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_ROLLBACK_REQUIRED"));
            print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_WARNING"), "warning");
        } elsif ($opt{destroy_clones} && !$in{'confirm_snapshot_rollback_clones'}) {
            print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_ROLLBACK_CLONES_REQUIRED"));
            print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_CLONES_WARNING"), "warning");
        } else {
            eval {
                zfs_rollback($snapshot_name, \%opt);
                log_info("Rolled back dataset $dataset_name to snapshot $snapshot_name");
                print &ui_print_success(L("SUCCESS_SNAPSHOT_ROLLBACK", $snapshot_name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SNAPSHOT_ROLLBACK_FAILED", $@));
            }
        }
    }

    print &ui_subheading("Rollback Snapshot: " . &html_escape($snapshot_name));
    print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_WARNING"), "warning");
    if ($opt{destroy_clones}) {
        print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_CLONES_WARNING"), "warning");
    }

    my @cmd_preview = ('zfs', 'rollback');
    push @cmd_preview, '-r' if $opt{destroy_newer};
    push @cmd_preview, '-R' if $opt{destroy_clones};
    push @cmd_preview, '-f' if $opt{force};
    push @cmd_preview, $snapshot_name;
    print "<p>" . L("MSG_REVIEW_COMMAND") . "</p>";
    print "<div class='zfsguru-danger-block'>" . &html_escape(join(' ', @cmd_preview)) . "</div>";

    print &ui_form_start("advanced_datasets.cgi", "post");
    print &ui_hidden("action", "rollback");
    print &ui_hidden("snapshot", $snapshot_name);
    print &ui_hidden("do_rollback", 1);
    print &ui_table_start(L("TABLE_SNAPSHOT_ACTIONS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_ROLLBACK"),
        &ui_checkbox("confirm_snapshot_rollback", 1, L("LBL_CONFIRM_SNAPSHOT_ROLLBACK"),
            ($in{'confirm_snapshot_rollback'} ? 1 : 0)));
    my $opts_html = join("<br>",
        &ui_checkbox("rollback_destroy_newer", 1, L("LBL_ROLLBACK_DESTROY_NEWER"), ($opt{destroy_newer} ? 1 : 0)),
        &ui_checkbox("rollback_destroy_clones", 1, L("LBL_ROLLBACK_DESTROY_CLONES"), ($opt{destroy_clones} ? 1 : 0)),
        &ui_checkbox("rollback_force", 1, L("LBL_ROLLBACK_FORCE"), ($opt{force} ? 1 : 0)),
    );
    print &ui_table_row(L("ROW_ROLLBACK_OPTIONS"), $opts_html);
    print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_ROLLBACK_CLONES"),
        &ui_checkbox("confirm_snapshot_rollback_clones", 1, L("LBL_CONFIRM_SNAPSHOT_ROLLBACK_CLONES"),
            ($in{'confirm_snapshot_rollback_clones'} ? 1 : 0)));
    print &ui_table_end();
    print &ui_submit(L("BTN_ROLLBACK"), "do_rollback", 0, "style='background:#f0ad4e;color:#fff;border-color:#eea236'") . " ";
    print &ui_link($back, L("BTN_CANCEL"));
    print &ui_form_end();
}

sub action_quotas {
    my $dataset_name = $in{'dataset'} || '';
    if (!is_dataset_name($dataset_name)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
        return;
    }
    
    if ($in{'save_quotas'}) {
        if ($in{'quota'}) {
            eval {
                zfs_set_quota($dataset_name, $in{'quota'});
                log_info("Set quota on $dataset_name: $in{quota}");
            };
        }
        if ($in{'refquota'}) {
            eval {
                zfs_set_refquota($dataset_name, $in{'refquota'});
                log_info("Set refquota on $dataset_name: $in{refquota}");
            };
        }
        if ($in{'reservation'}) {
            eval {
                zfs_set_reservation($dataset_name, $in{'reservation'});
                log_info("Set reservation on $dataset_name: $in{reservation}");
            };
        }
        print &ui_print_success(L("SUCCESS_QUOTAS_UPDATED"));
    }
    
    my $props = zfs_get($dataset_name, 'quota', 'refquota', 'reservation');
    
    print &ui_subheading(L("SUB_QUOTAS_FOR", $dataset_name));
    print &ui_form_start("advanced_datasets.cgi", "post");
    print &ui_hidden("action", "quotas");
    print &ui_hidden("dataset", $dataset_name);
    print &ui_hidden("save_quotas", 1);
    
    print &ui_table_start(L("TABLE_QUOTA_SETTINGS"), "width=100%", 2);
    
    my $quota_val = '';
    my $refquota_val = '';
    my $reservation_val = '';
    
    if (ref($props) eq 'HASH') {
        $quota_val = $props->{quota} if exists $props->{quota};
        $refquota_val = $props->{refquota} if exists $props->{refquota};
        $reservation_val = $props->{reservation} if exists $props->{reservation};
    }
    
    print &ui_table_row(L("ROW_QUOTA_TOTAL"), &ui_textbox("quota", $quota_val, 20) .
        "<br><small>" . L("HINT_QUOTA_TOTAL") . "</small>");
    print &ui_table_row(L("ROW_REFQUOTA"), &ui_textbox("refquota", $refquota_val, 20) .
        "<br><small>" . L("HINT_REFQUOTA") . "</small>");
    print &ui_table_row(L("ROW_RESERVATION"), &ui_textbox("reservation", $reservation_val, 20) .
        "<br><small>" . L("HINT_RESERVATION") . "</small>");
    
    print &ui_table_end();
    print &ui_form_end([ [ "save_quotas", L("BTN_SAVE_QUOTAS") ] ]);
}

sub action_properties {
    my $dataset_name = $in{'dataset'} || '';
    if (!is_dataset_name($dataset_name)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
        return;
    }

    my @editable = qw(
        atime compression recordsize sync
        acltype aclinherit aclmode xattr
        exec canmount mountpoint
        copies dedup
    );

    my %allowed = map { $_ => 1 } @editable;
    my %props = ();
    my $zfs_cmd = $zfsguru_lib::ZFS || '/sbin/zfs';
    my ($rc, $out, $err) = run_cmd($zfs_cmd, 'get', '-H', '-o', 'property,value,source', join(',', @editable), $dataset_name);
    if ($rc == 0 && defined $out && $out =~ /\S/) {
        for my $ln (split /\n/, $out) {
            my ($k, $v, $src) = split /\t+|\s+/, $ln, 3;
            next unless defined $k && $allowed{$k};
            $props{$k} = {
                value  => defined($v) ? $v : '',
                source => defined($src) ? $src : '-',
            };
        }
    } else {
        my $all_props = zfs_get($dataset_name);
        for my $k (@editable) {
            $props{$k} = {
                value  => (ref($all_props) eq 'HASH' && defined $all_props->{$k}) ? $all_props->{$k} : '',
                source => '-',
            };
        }
    }

    if ($in{'save_props'}) {
        eval {
            for my $p (@editable) {
                my $field = "prop_$p";
                next unless exists $in{$field};
                my $value = defined($in{$field}) ? $in{$field} : '';

                if ($p eq 'mountpoint' && ($in{'prop_mountpoint_mode'} || '') eq 'inherit') {
                    zfs_inherit($dataset_name, $p);
                    next;
                }
                if ($value eq '__INHERIT__') {
                    zfs_inherit($dataset_name, $p);
                    next;
                }
                if ($p eq 'mountpoint' && $value ne '' && $value ne 'none' && $value ne 'legacy' && !is_mountpoint($value)) {
                    die L("ERR_MOUNTPOINT_INVALID", $value);
                }
                next if $value eq '';
                zfs_set($dataset_name, $p, $value);
            }
            if ($in{'acl_inherit_fd'}) {
                my ($ok_fd, $msg_fd) = apply_fd_acl_flags_for_dataset($dataset_name);
                if (!$ok_fd) {
                    log_warn("Dataset properties updated but ACL :fd flag apply skipped/failed for $dataset_name: $msg_fd");
                } else {
                    log_info("Applied ACL :fd inheritance flags for dataset $dataset_name");
                }
            }
            log_info("Updated properties for $dataset_name");
            print &ui_print_success(L("SUCCESS_PROPERTIES_UPDATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PROPERTIES_UPDATE_FAILED", $@));
        }
        # Refresh values after save
        %props = ();
        my ($rc2, $out2, $err2) = run_cmd($zfs_cmd, 'get', '-H', '-o', 'property,value,source', join(',', @editable), $dataset_name);
        if ($rc2 == 0 && defined $out2 && $out2 =~ /\S/) {
            for my $ln (split /\n/, $out2) {
                my ($k, $v, $src) = split /\t+|\s+/, $ln, 3;
                next unless defined $k && $allowed{$k};
                $props{$k} = {
                    value  => defined($v) ? $v : '',
                    source => defined($src) ? $src : '-',
                };
            }
        }
    }

    print &ui_subheading(L("SUB_DATASET_PROPERTIES", $dataset_name));
    print &ui_form_start("advanced_datasets.cgi", "post");
    print &ui_hidden("action", "properties");
    print &ui_hidden("dataset", $dataset_name);
    print &ui_hidden("save_props", 1);

    my $inherit_label = L("LBL_INHERIT");
    my @yesno_inherit = (
        [ "on", "on" ],
        [ "off", "off" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @recordsize_opts = (
        [ "512", "512B" ], [ "1K", "1K" ], [ "2K", "2K" ], [ "4K", "4K" ],
        [ "8K", "8K" ], [ "16K", "16K" ], [ "32K", "32K" ], [ "64K", "64K" ],
        [ "128K", "128K (General default)" ], [ "256K", "256K" ], [ "512K", "512K" ],
        [ "1M", "1M (Media/Large file default)" ], [ "2M", "2M" ], [ "4M", "4M" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @compression_opts = (
        [ "lz4", "lz4 (recommended)" ],
        [ "zstd-1", "zstd-1" ],
        [ "zstd", "zstd" ],
        [ "zstd-6", "zstd-6" ],
        [ "zstd-9", "zstd-9" ],
        [ "zstd-19", "zstd-19" ],
        [ "off", "off" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @sync_opts = (
        [ "standard", "standard (default)" ],
        [ "always", "always" ],
        [ "disabled", "disabled" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @acltype_opts = (
        [ "nfsv4", "nfsv4" ],
        [ "posix", "posix" ],
        [ "off", "off" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @aclinherit_opts = (
        [ "passthrough", "passthrough" ],
        [ "passthrough-x", "passthrough-x (:fd)" ],
        [ "restricted", "restricted" ],
        [ "noallow", "noallow" ],
        [ "discard", "discard" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @aclmode_opts = (
        [ "passthrough", "passthrough" ],
        [ "restricted", "restricted" ],
        [ "groupmask", "groupmask" ],
        [ "discard", "discard" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @xattr_opts = (
        [ "sa", "sa" ],
        [ "on", "on" ],
        [ "off", "off" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @canmount_opts = (
        [ "on", "on" ],
        [ "off", "off" ],
        [ "noauto", "noauto" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @copies_opts = (
        [ "1", "1" ],
        [ "2", "2" ],
        [ "3", "3" ],
        [ "__INHERIT__", $inherit_label ],
    );
    my @dedup_opts = (
        [ "off", "off" ],
        [ "on", "on" ],
        [ "verify", "verify" ],
        [ "sha256", "sha256" ],
        [ "__INHERIT__", $inherit_label ],
    );

    my $render_prop_row = sub {
        my ($prop) = @_;
        my $val = exists $props{$prop} ? ($props{$prop}{value} // '') : '';
        my $src = exists $props{$prop} ? ($props{$prop}{source} // '-') : '-';
        my $input;

        if ($prop eq 'atime' || $prop eq 'exec') {
            $input = &ui_select("prop_$prop", $val, \@yesno_inherit);
        } elsif ($prop eq 'recordsize') {
            $input = &ui_select("prop_$prop", $val, \@recordsize_opts);
        } elsif ($prop eq 'compression') {
            $input = &ui_select("prop_$prop", $val, \@compression_opts);
        } elsif ($prop eq 'sync') {
            $input = &ui_select("prop_$prop", $val, \@sync_opts);
        } elsif ($prop eq 'acltype') {
            $input = &ui_select("prop_$prop", $val, \@acltype_opts);
        } elsif ($prop eq 'aclinherit') {
            $input = &ui_select("prop_$prop", $val, \@aclinherit_opts);
        } elsif ($prop eq 'aclmode') {
            $input = &ui_select("prop_$prop", $val, \@aclmode_opts);
        } elsif ($prop eq 'xattr') {
            $input = &ui_select("prop_$prop", $val, \@xattr_opts);
        } elsif ($prop eq 'canmount') {
            $input = &ui_select("prop_$prop", $val, \@canmount_opts);
        } elsif ($prop eq 'copies') {
            $input = &ui_select("prop_$prop", $val, \@copies_opts);
        } elsif ($prop eq 'dedup') {
            $input = &ui_select("prop_$prop", $val, \@dedup_opts);
        } elsif ($prop eq 'mountpoint') {
            my $mode_default = ($src =~ /^inherited\b/i) ? 'inherit' : 'set';
            my $mode = defined $in{'prop_mountpoint_mode'} ? $in{'prop_mountpoint_mode'} : $mode_default;
            $input = &ui_filebox("prop_$prop", $val, 40, 0, undef, undef, 1) . " " .
                     &ui_select("prop_mountpoint_mode", $mode, [
                        [ "set", "set value" ],
                        [ "inherit", $inherit_label ],
                     ]);
        } else {
            $input = &ui_textbox("prop_$prop", $val, 30);
        }

        print &ui_table_row($prop, $input . " " . L("LABEL_FROM_SOURCE", $src));
    };

    print &ui_table_start("Performance", "width=100%", 2);
    for my $p (qw(compression recordsize sync atime)) { $render_prop_row->($p); }
    print &ui_table_end();

    my $acltype_props_val = exists $props{'acltype'} ? (($props{'acltype'}{value} // '')) : '';
    my $acl_fd_props_default = defined $in{'acl_inherit_fd'}
        ? ($in{'acl_inherit_fd'} ? 1 : 0)
        : (lc($acltype_props_val) eq 'nfsv4' ? 1 : 0);

    print &ui_table_start("ACL & Permissions", "width=100%", 2);
    for my $p (qw(acltype aclinherit aclmode xattr exec canmount)) { $render_prop_row->($p); }
    print &ui_table_row("ACL inherit flags", &ui_checkbox("acl_inherit_fd", 1, "Add :fd to base NFSv4 ACL entries", $acl_fd_props_default));
    print &ui_table_end();

    print &ui_table_start("Space & Mount", "width=100%", 2);
    for my $p (qw(copies dedup mountpoint)) { $render_prop_row->($p); }
    print &ui_table_end();

    print &ui_form_end([ [ "save_props", L("BTN_SAVE_PROPERTIES") ] ]);
}

sub action_rename {
    my $dataset_name = $in{'dataset'} || '';
    if (!is_dataset_name($dataset_name)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset_name));
        return;
    }
    
    if ($in{'do_rename'}) {
        my $new_name = $in{'new_dataset_name'};
        if (!is_dataset_name($new_name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $new_name));
            return;
        }
        eval {
            zfs_rename($dataset_name, $new_name);
            log_info("Renamed dataset: $dataset_name -> $new_name");
            print &ui_print_success(L("SUCCESS_DATASET_RENAMED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DATASET_RENAME_FAILED", $@));
        }
        return;
    }
    
    print &ui_subheading(L("SUB_RENAME_DATASET"));
    print &ui_form_start("advanced_datasets.cgi", "post");
    print &ui_hidden("action", "rename");
    print &ui_hidden("dataset", $dataset_name);
    print &ui_hidden("do_rename", 1);
    
    my $rename_default = exists $in{'new_dataset_name'} ? ($in{'new_dataset_name'} // '') : $dataset_name;
    print &ui_table_start(L("TABLE_RENAME_CONFIG"), "width=100%", 2);
    print &ui_table_row(L("ROW_CURRENT_NAME"), &html_escape($dataset_name));
    print &ui_table_row(L("ROW_NEW_NAME"), &ui_textbox("new_dataset_name", $rename_default, 40));
    print &ui_table_end();
    
    print &ui_form_end([ [ "do_rename", L("BTN_RENAME") ] ]);
}

1;
