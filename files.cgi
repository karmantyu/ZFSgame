#!/usr/bin/env perl

package main;

use strict;
use warnings;
use Cwd qw(realpath);
use File::Basename qw(dirname);
use POSIX qw(strftime);
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

our %config;

zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => "TITLE_FILES");

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

my $action = $in{'action'} || 'filesystems';
my $advanced_enabled = $config{'advanced_mode'} ? 1 : 0;

my @tabs_list = (
    [ 'filesystems', 'TAB_FILESYSTEMS' ],
    [ 'browse',      'TAB_FILE_BROWSER' ],
    [ 'snapshots',   'TAB_SNAPSHOTS' ],
    [ 'volumes',     'TAB_VOLUMES' ],
    [ 'permissions', 'TAB_PERMISSIONS' ],
);
@tabs_list = grep { $_->[0] ne 'volumes' } @tabs_list unless $advanced_enabled;

my $active_tab = $action;
if ($action eq 'query' || $action eq 'destroy') {
    $active_tab = 'filesystems';
}
if (!$advanced_enabled && $action eq 'volumes') {
    $active_tab = 'filesystems';
}

print zfsguru_print_tabs(
    script => 'files.cgi',
    active => $active_tab,
    tabs   => \@tabs_list,
);

if (!$advanced_enabled && $action eq 'volumes') {
    &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
    $action = 'filesystems';
}

if ($action eq 'filesystems') {
    action_filesystems();
} elsif ($action eq 'query') {
    action_query();
} elsif ($action eq 'destroy') {
    action_destroy();
} elsif ($action eq 'browse') {
    action_browse();
} elsif ($action eq 'snapshots') {
    action_snapshots();
} elsif ($action eq 'volumes') {
    action_volumes();
} elsif ($action eq 'permissions') {
    action_permissions();
}

my $back_url = 'index.cgi';
if ($action ne 'filesystems') {
    $back_url = 'files.cgi?action=filesystems';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_filesystems {
    print &ui_subheading(L("SUB_FILESYSTEMS"));

    my $datasets = zfs_list([qw(name used avail refer mountpoint)], '-t', 'filesystem');

    my @heads = (
        L("COL_FILESYSTEM"),
        L("COL_USED"),
        L("COL_AVAILABLE"),
        L("COL_REFERENCED"),
        L("COL_MOUNT_POINT"),
        L("COL_ACTIONS"),
    );

    my @data;
    for my $ds (@$datasets) {
        my $name = $ds->{name} || '';
        next unless length $name;

        my $mount = $ds->{mountpoint} || '-';
        my $mount_disp = &html_escape($mount);
        if ($mount eq '-' || $mount eq 'legacy') {
            $mount_disp = "<i>" . &html_escape($mount) . "</i>";
        } elsif ($mount =~ m{^/}) {
            $mount_disp = "<a href='files.cgi?action=browse&path=" .
                          &url_encode($mount) . "'>" . &html_escape($mount) . "</a>";
        }

        my $actions = join(' ',
            "<a class='button' href='advanced_datasets.cgi?action=view&dataset=" .
                &url_encode($name) . "'>" . L("BTN_DETAILS") . "</a>",
            "<a class='button' href='files.cgi?action=query&dataset=" .
                &url_encode($name) . "'>" . L("BTN_QUERY") . "</a>",
            "<a class='button' href='advanced_datasets.cgi?action=snapshots&dataset=" .
                &url_encode($name) . "'>" . L("BTN_SNAPSHOTS") . "</a>",
            "<a class='button' href='advanced_datasets.cgi?action=quotas&dataset=" .
                &url_encode($name) . "'>" . L("BTN_QUOTAS") . "</a>",
            "<a class='button' href='advanced_datasets.cgi?action=properties&dataset=" .
                &url_encode($name) . "'>" . L("BTN_PROPERTIES") . "</a>",
            "<a class='button' href='files.cgi?action=destroy&dataset=" .
                &url_encode($name) . "'>" . L("BTN_DESTROY_FILESYSTEM") . "</a>",
            "<a class='button' href='advanced_datasets.cgi?action=delete&dataset=" .
                &url_encode($name) . "'>" . L("BTN_DELETE_DATASET") . "</a>"
        );

        push @data, [
            &html_escape($name),
            &html_escape($ds->{used} || '-'),
            &html_escape($ds->{avail} || '-'),
            &html_escape($ds->{refer} || '-'),
            $mount_disp,
            $actions,
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1,
        L("TABLE_FILESYSTEMS"), L("ERR_NO_FILESYSTEMS_FOUND"));
}

sub action_query {
    print &ui_subheading(L("SUB_FILESYSTEM_QUERY"));
    print "<p>" . L("MSG_FILESYSTEM_QUERY_HELP") . "</p>";

    my $dataset = $in{'dataset'} || $in{'query'} || '';
    $dataset =~ s/^\s+|\s+$//g;

    my $datasets = zfs_list([qw(name mountpoint)], '-t', 'filesystem');
    my @opts = map {
        my $mp = $_->{mountpoint} || '-';
        [ $_->{name}, $_->{name} . " ($mp)" ]
    } sort { $a->{name} cmp $b->{name} } @$datasets;
    unshift @opts, [ '', L("VALUE_SELECT_FILESYSTEM") ];

    print &ui_form_start("files.cgi", "get");
    print &ui_hidden("action", "query");
    print &ui_table_start(L("TABLE_QUERY_SELECT"), "width=100%", 2);
    print &ui_table_row(L("ROW_FILESYSTEM"), &ui_select("dataset", $dataset, \@opts));
    print &ui_table_end();
    print &ui_form_end([ [ "go", L("BTN_QUERY") ] ]);

    return unless length $dataset;
    if (!is_dataset_name($dataset)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset));
        return;
    }

    if ($in{'save_query_props'}) {
        my @props = qw(mountpoint atime readonly compression dedup copies checksum sync primarycache secondarycache recordsize quota);

        my %allowed = (
            atime => { on => 1, off => 1 },
            readonly => { on => 1, off => 1 },
            dedup => { off => 1, on => 1, verify => 1, sha256 => 1, 'sha256,verify' => 1 },
            copies => { 1 => 1, 2 => 1, 3 => 1 },
            checksum => { on => 1, off => 1, fletcher4 => 1, sha256 => 1, sha512 => 1 },
            sync => { standard => 1, always => 1, disabled => 1 },
            primarycache => { all => 1, none => 1, metadata => 1 },
            secondarycache => { all => 1, none => 1, metadata => 1 },
        );

        my %allowed_compression;
        for my $v (qw(off lz4 lzjb zle gzip zstd)) { $allowed_compression{$v} = 1; }
        for my $i (1 .. 9) { $allowed_compression{"gzip-$i"} = 1; }
        for my $i (1 .. 19) { $allowed_compression{"zstd-$i"} = 1; }

        my %set;
        my @inherit;
        for my $p (@props) {
            if ($in{"inherit_$p"}) {
                push @inherit, $p;
                next;
            }

            my $v = $in{"prop_$p"};
            $v = '' if !defined $v;
            $v =~ s/^\s+|\s+$//g;
            next if $v eq '';

            if ($p eq 'mountpoint') {
                my $lc = lc($v);
                if ($lc eq 'legacy' || $lc eq 'none') {
                    $v = $lc;
                } elsif (!is_mountpoint($v)) {
                    print &ui_print_error(L("ERR_MOUNTPOINT_INVALID", $v));
                    return;
                }
            } elsif ($p eq 'quota') {
                my $lc = lc($v);
                if ($lc eq 'none') {
                    $v = 'none';
                } elsif (!is_zfs_size($v)) {
                    print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", $p, $v));
                    return;
                }
            } elsif ($p eq 'compression') {
                if (!$allowed_compression{$v}) {
                    print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", $p, $v));
                    return;
                }
            } elsif ($p eq 'recordsize') {
                if (!is_zfs_size($v)) {
                    print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", $p, $v));
                    return;
                }
            } else {
                if (!$allowed{$p} || !$allowed{$p}{$v}) {
                    print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", $p, $v));
                    return;
                }
            }

            $set{$p} = $v;
        }

        eval {
            for my $p (@inherit) {
                zfs_inherit($dataset, $p, 0);
                log_info("Inherited property '$p' on '$dataset'");
            }
            if (%set) {
                zfs_set($dataset, \%set);
                log_info("Updated filesystem properties on '$dataset'");
            }
            print &ui_print_success(L("SUCCESS_PROPERTIES_UPDATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PROPERTIES_UPDATE_FAILED", $@));
        }
    }

    my $info = zfs_list([qw(name used avail refer mountpoint)], '-t', 'filesystem', $dataset);
    if (!$info || !@$info) {
        print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
        return;
    }

    my $ds = $info->[0];

    my @props_edit = qw(mountpoint atime readonly compression dedup copies checksum sync primarycache secondarycache recordsize quota);
    my @props_show = (@props_edit, qw(sharenfs creation compressratio usedbysnapshots usedbychildren));
    my $rows = zfs_get($dataset, \@props_show);
    my (%val, %src);
    for my $r (@$rows) {
        $val{$r->{property}} = $r->{value};
        $src{$r->{property}} = $r->{source};
    }

    # Legacy query page shows a couple of extra utilization metrics; keep them here for parity.
    print &ui_subheading(L("SUB_DATASET", $dataset));
    print &ui_table_start(L("TABLE_DATASET_INFO"), "width=100%", 2);
    print &ui_table_row(L("COL_NAME"), &html_escape($ds->{name} || $dataset));
    print &ui_table_row(L("COL_USED"), &html_escape($ds->{used} || '-'));
    print &ui_table_row(L("COL_AVAILABLE"), &html_escape($ds->{avail} || '-'));
    print &ui_table_row(L("COL_REFERENCED"), &html_escape($ds->{refer} || '-'));
    print &ui_table_row(L("COL_MOUNT_POINT"), &html_escape($ds->{mountpoint} || '-'));
    print &ui_table_row(L("COL_CREATION_DATE"), &html_escape($val{creation} || '-'));
    print &ui_table_row(L("ROW_COMPRESSION_RATIO"), &html_escape($val{compressratio} || '-'));
    print &ui_table_row(L("ROW_USED_BY_SNAPSHOTS"), &html_escape($val{usedbysnapshots} || '-'));
    print &ui_table_row(L("ROW_USED_BY_CHILDREN"), &html_escape($val{usedbychildren} || '-'));
    print &ui_table_end();

    my $from_src = sub {
        my ($p) = @_;
        my $s = $src{$p} || '';
        return '' if $s eq '';
        return " <span class='zfsguru-muted'>" . L("LABEL_FROM_SOURCE", &html_escape($s)) . "</span>";
    };

    my $smb_share_for_path = sub {
        my ($path) = @_;
        return '' unless defined $path && $path =~ m{^/};

        my $raw = read_file_text('/usr/local/etc/smb4.conf');
        return '' unless defined $raw && length $raw;

        my $cur = '';
        my $cur_orig = '';
        for my $line (split(/\n/, $raw)) {
            $line =~ s/\r$//;
            $line =~ s/^\s+|\s+$//g;
            next if $line eq '' || $line =~ /^[;#]/;

            if ($line =~ /^\[(.+?)\]$/) {
                $cur_orig = $1;
                $cur = lc($1);
                next;
            }
            next if !$cur || $cur eq 'global';

            if ($line =~ /^path\s*=\s*(.+)$/i) {
                my $p = $1;
                $p =~ s/\s*[;#].*$//;
                $p =~ s/^\s+|\s+$//g;
                $p =~ s/^\"(.*)\"$/$1/;
                $p =~ s/^'(.*)'$/$1/;
                return $cur_orig if defined $p && $p eq $path;
            }
        }

        return '';
    };

    my $mp = $val{mountpoint};
    $mp = $ds->{mountpoint} if !defined $mp;
    $mp = '' if !defined $mp;
    $mp =~ s/^\s+|\s+$//g;

    my $sharenfs = $val{sharenfs} // '';
    $sharenfs =~ s/^\s+|\s+$//g;
    my $nfs_shared = ($mp =~ m{^/} && $sharenfs ne '' && $sharenfs ne '-' && lc($sharenfs) ne 'off') ? 1 : 0;
    my $nfs_status = $nfs_shared ? L("VALUE_SHARED") : L("VALUE_NOT_SHARED");

    my $smb_share = ($mp =~ m{^/}) ? $smb_share_for_path->($mp) : '';
    my $smb_shared = ($smb_share && length $smb_share) ? 1 : 0;
    my $smb_status = $smb_shared ? L("VALUE_SHARED") : L("VALUE_NOT_SHARED");

    print &ui_hr();
    print &ui_subheading(L("SUB_DATASET_SHARING", $dataset));
    print &ui_table_start(L("TABLE_DATASET_SHARING"), "width=100%", 2);
    print &ui_table_row(L("ROW_MOUNTPOINT"), &html_escape($mp || '-'));
    my $nfs_actions = "<a class='button' href='access.cgi?action=nfs&dataset=" . &url_encode($dataset) . "'>" .
                      L("TAB_NFS_ACCESS") . "</a>";
    my $nfs_detail = $nfs_status . " (" . &html_escape($sharenfs || 'off') . ")" . $from_src->('sharenfs');
    if ($mp !~ m{^/}) {
        $nfs_detail = L("VALUE_UNKNOWN");
    }
    print &ui_table_row(L("ROW_NFS_SHARE_STATUS"), $nfs_detail . " " . $nfs_actions);

    my $smb_actions = "<a class='button' href='access.cgi?action=smb_shares'>" .
                      L("TAB_SMB_SHARES") . "</a>";
    my $smb_detail = $mp =~ m{^/}
        ? ($smb_shared ? ($smb_status . ": " . &html_escape($smb_share)) : $smb_status)
        : L("VALUE_UNKNOWN");
    print &ui_table_row(L("ROW_SMB_SHARE_STATUS"), $smb_detail . " " . $smb_actions);
    print &ui_table_end();

    print "<p>" .
          "<a class='button' href='files.cgi?action=snapshots&dataset=" . &url_encode($dataset) . "'>" . L("BTN_SNAPSHOTS") . "</a> " .
          "<a class='button' href='advanced_datasets.cgi?action=quotas&dataset=" . &url_encode($dataset) . "'>" . L("BTN_QUOTAS") . "</a> " .
          "<a class='button' href='advanced_datasets.cgi?action=properties&dataset=" . &url_encode($dataset) . "'>" . L("BTN_PROPERTIES") . "</a>" .
          "</p>";

    my @compression_opts = (
        [ 'off', 'off' ],
        [ 'lz4', 'lz4' ],
        [ 'zstd', 'zstd' ],
        (map { [ "zstd-$_", "zstd-$_" ] } (1 .. 19)),
        [ 'gzip', 'gzip' ],
        (map { [ "gzip-$_", "gzip-$_" ] } (1 .. 9)),
        [ 'lzjb', 'lzjb' ],
        [ 'zle', 'zle' ],
    );

    my @dedup_opts = (
        [ 'off', 'off' ],
        [ 'on', 'on' ],
        [ 'verify', 'verify' ],
        [ 'sha256', 'sha256' ],
        [ 'sha256,verify', 'sha256,verify' ],
    );

    my @copies_opts = (
        [ '1', '1' ],
        [ '2', '2' ],
        [ '3', '3' ],
    );

    my @checksum_opts = (
        [ 'on', 'on' ],
        [ 'fletcher4', 'fletcher4' ],
        [ 'sha256', 'sha256' ],
        [ 'sha512', 'sha512' ],
        [ 'off', 'off' ],
    );

    my @sync_opts = (
        [ 'standard', 'standard' ],
        [ 'always', 'always' ],
        [ 'disabled', 'disabled' ],
    );

    my @cache_opts = (
        [ 'all', 'all' ],
        [ 'metadata', 'metadata' ],
        [ 'none', 'none' ],
    );

    my @onoff_opts = (
        [ 'on', 'on' ],
        [ 'off', 'off' ],
    );

    my @recordsize_opts = (
        [ '4K', '4K' ],
        [ '8K', '8K' ],
        [ '16K', '16K' ],
        [ '32K', '32K' ],
        [ '64K', '64K' ],
        [ '128K', '128K' ],
        [ '256K', '256K' ],
        [ '512K', '512K' ],
        [ '1M', '1M' ],
    );

    print &ui_subheading(L("SUB_DATASET_PROPERTIES", $dataset));
    print &ui_form_start("files.cgi", "post");
    print &ui_hidden("action", "query");
    print &ui_hidden("dataset", $dataset);
    print &ui_hidden("save_query_props", 1);

    print &ui_table_start(L("TABLE_FILESYSTEM_QUERY_PROPS"), "width=100%", 2);
    print &ui_table_row(L("ROW_MOUNTPOINT"),
        &ui_textbox("prop_mountpoint", ($val{mountpoint} // ''), 60) .
        "<br><small>" . L("HINT_MOUNTPOINT_QUERY") . "</small>" . " " .
        &ui_checkbox("inherit_mountpoint", 1, L("LBL_INHERIT"), 0) . $from_src->('mountpoint'));
    print &ui_table_row(L("ROW_ATIME"),
        &ui_select("prop_atime", ($val{atime} // 'on'), \@onoff_opts) . " " .
        &ui_checkbox("inherit_atime", 1, L("LBL_INHERIT"), 0) . $from_src->('atime'));
    print &ui_table_row(L("ROW_READONLY"),
        &ui_select("prop_readonly", ($val{readonly} // 'off'), \@onoff_opts) . " " .
        &ui_checkbox("inherit_readonly", 1, L("LBL_INHERIT"), 0) . $from_src->('readonly'));
    print &ui_table_row(L("ROW_COMPRESSION"),
        &ui_select("prop_compression", ($val{compression} // 'off'), \@compression_opts) . " " .
        &ui_checkbox("inherit_compression", 1, L("LBL_INHERIT"), 0) . $from_src->('compression'));
    print &ui_table_row(L("ROW_DEDUPLICATION"),
        &ui_select("prop_dedup", ($val{dedup} // 'off'), \@dedup_opts) . " " .
        &ui_checkbox("inherit_dedup", 1, L("LBL_INHERIT"), 0) . $from_src->('dedup'));
    print &ui_table_row(L("ROW_COPIES"),
        &ui_select("prop_copies", ($val{copies} // '1'), \@copies_opts) . " " .
        &ui_checkbox("inherit_copies", 1, L("LBL_INHERIT"), 0) . $from_src->('copies'));
    print &ui_table_row(L("ROW_CHECKSUM"),
        &ui_select("prop_checksum", ($val{checksum} // 'on'), \@checksum_opts) . " " .
        &ui_checkbox("inherit_checksum", 1, L("LBL_INHERIT"), 0) . $from_src->('checksum'));
    print &ui_table_row(L("ROW_SYNC"),
        &ui_select("prop_sync", ($val{sync} // 'standard'), \@sync_opts) . " " .
        &ui_checkbox("inherit_sync", 1, L("LBL_INHERIT"), 0) . $from_src->('sync'));
    print &ui_table_row(L("ROW_PRIMARYCACHE"),
        &ui_select("prop_primarycache", ($val{primarycache} // 'all'), \@cache_opts) . " " .
        &ui_checkbox("inherit_primarycache", 1, L("LBL_INHERIT"), 0) . $from_src->('primarycache'));
    print &ui_table_row(L("ROW_SECONDARYCACHE"),
        &ui_select("prop_secondarycache", ($val{secondarycache} // 'all'), \@cache_opts) . " " .
        &ui_checkbox("inherit_secondarycache", 1, L("LBL_INHERIT"), 0) . $from_src->('secondarycache'));
    print &ui_table_row(L("ROW_RECORDSIZE"),
        &ui_select("prop_recordsize", ($val{recordsize} // '128K'), \@recordsize_opts) . " " .
        &ui_checkbox("inherit_recordsize", 1, L("LBL_INHERIT"), 0) . $from_src->('recordsize'));
    print &ui_table_row(L("ROW_QUOTA_TOTAL"),
        &ui_textbox("prop_quota", ($val{quota} // ''), 20) .
        "<br><small>" . L("HINT_QUOTA_TOTAL") . "</small>" . " " .
        &ui_checkbox("inherit_quota", 1, L("LBL_INHERIT"), 0) . $from_src->('quota'));

    print &ui_table_end();
    print &ui_form_end([ [ "save_query_props", L("BTN_SAVE_PROPERTIES") ] ]);
}

sub action_destroy {
    print &ui_subheading(L("SUB_FILESYSTEM_DESTROY"));
    print "<p>" . L("MSG_FILESYSTEM_DESTROY_HELP") . "</p>";

    my $dataset = $in{'dataset'} || $in{'destroy'} || '';
    $dataset =~ s/^\s+|\s+$//g;

    my $datasets = zfs_list([qw(name mountpoint)], '-t', 'filesystem');
    my @opts = map {
        my $mp = $_->{mountpoint} || '-';
        [ $_->{name}, $_->{name} . " ($mp)" ]
    } sort { $a->{name} cmp $b->{name} } @$datasets;
    unshift @opts, [ '', L("VALUE_SELECT_FILESYSTEM") ];

    print &ui_form_start("files.cgi", "get");
    print &ui_hidden("action", "destroy");
    print &ui_table_start(L("TABLE_DESTROY_SELECT"), "width=100%", 2);
    print &ui_table_row(L("ROW_FILESYSTEM"), &ui_select("dataset", $dataset, \@opts));
    print &ui_table_end();
    print &ui_form_end([ [ "go", L("BTN_QUERY") ] ]);

    return unless length $dataset;
    if (!is_dataset_name($dataset)) {
        print &ui_print_error(L("ERR_INVALID_DATASET", $dataset));
        return;
    }

    my $impact = zfs_list([qw(name type used avail refer mountpoint)], '-r', $dataset, '-t', 'all');
    if (!$impact || !@$impact) {
        print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
        return;
    }

    print &ui_alert(L("MSG_DATASET_DESTROY_WARNING"), "danger");

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

    my $del_url = "advanced_datasets.cgi?action=delete&dataset=" . &url_encode($dataset);
    print "<p><a class='button' href='" . &html_escape($del_url) . "'>" . &html_escape(L("BTN_DELETE_DATASET")) . "</a></p>";
}

sub action_browse {
    print &ui_subheading(L("SUB_FILE_BROWSER"));
    print "<p>" . L("MSG_FILE_BROWSER_READONLY") . "</p>";
    print &ui_alert(L("MSG_FILE_BROWSER_MINIMAL_NOTE"), "info");

    my $path = $in{'path'} || '/';
    $path =~ s/^\s+|\s+$//g;
    $path = '/' if !$path || $path !~ m{^/};

    my $show_hidden = $in{'show_hidden'} ? 1 : 0;
    my $preview_lines = $in{'preview_lines'} || 60;
    $preview_lines = 10 if $preview_lines !~ /^\d+$/ || $preview_lines < 10;
    $preview_lines = 400 if $preview_lines > 400;

    my $real = eval { realpath($path) };
    if (!$real && ($path =~ m{^/}) && (-e $path || -l $path)) {
        $real = $path;
    }
    if (!$real || $real !~ m{^/}) {
        print &ui_print_error(L("ERR_BROWSE_PATH_INVALID"));
        return;
    }

    if (!-e $real && !-l $real) {
        print &ui_print_error(L("ERR_BROWSE_NOT_FOUND", $real));
        return;
    }

    print &ui_form_start("files.cgi", "get");
    print &ui_hidden("action", "browse");
    print &ui_table_start(L("TABLE_BROWSE"), "width=100%", 2);
    print &ui_table_row(L("ROW_PATH"), &ui_textbox("path", $real, 80));
    print &ui_table_row(
        L("ROW_SHOW_HIDDEN"),
        &ui_checkbox("show_hidden", 1, L("LBL_SHOW_HIDDEN"), $show_hidden)
    );
    print &ui_table_row(
        L("ROW_PREVIEW_LINES"),
        &ui_textbox("preview_lines", $preview_lines, 6) .
        " <span class='zfsguru-muted'>" . L("HINT_PREVIEW_LINES") . "</span>"
    );
    print &ui_table_end();
    print &ui_form_end([ [ "browse", L("BTN_BROWSE") ] ]);

    if ($real ne '/') {
        my $parent = dirname($real);
        $parent = '/' if !defined $parent || $parent eq '';
        my $up = "files.cgi?action=browse&path=" . &url_encode($parent) .
                 "&show_hidden=" . ($show_hidden ? 1 : 0) .
                 "&preview_lines=" . $preview_lines;
        print "<p><a href='" . &html_escape($up) . "'>" . &html_escape(L("LINK_PARENT_DIR")) . "</a></p>";
    }

    my $human_size = sub {
        my ($bytes) = @_;
        return '-' unless defined $bytes && $bytes =~ /^\d+$/;
        my $b = $bytes + 0;
        my @u = ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB');
        my $i = 0;
        while ($b >= 1024 && $i < $#u) {
            $b /= 1024;
            $i++;
        }
        my $s = $i == 0 ? sprintf("%d", $b) : sprintf("%.1f", $b);
        $s =~ s/\.0$//;
        return "$s $u[$i]";
    };

    my $file_preview = sub {
        my ($target, $line_cap, $byte_cap) = @_;
        $line_cap ||= 60;
        $byte_cap ||= 131072;
        return (undef, 0, 0, "not regular file") unless -f $target;

        open my $fh, '<', $target or return (undef, 0, 0, "open failed: $!");
        binmode($fh);
        my $buf = '';
        my $n = read($fh, $buf, $byte_cap);
        close $fh;
        return (undef, 0, 0, "read failed") unless defined $n;

        if ($buf =~ /[\x00-\x08\x0B\x0C\x0E-\x1F]/) {
            return ('', 0, 1, undef);
        }

        my @lines = split(/\n/, $buf, -1);
        my $trunc = 0;
        if (@lines > $line_cap) {
            @lines = @lines[0 .. ($line_cap - 1)];
            $trunc = 1;
        }
        $trunc = 1 if $n >= $byte_cap;
        my $txt = join("\n", @lines);
        return ($txt, $trunc, 0, undef);
    };

    if (!-d $real) {
        my @st = stat($real);
        my $perm = @st ? sprintf("%04o", ($st[2] & 07777)) : '-';
        my $mtime = @st ? scalar(localtime($st[9] || 0)) : '-';
        my $size = @st ? $human_size->($st[7] || 0) : '-';

        print &ui_table_start(L("TABLE_FILE_INFO"), "width=100%", 2);
        print &ui_table_row(L("ROW_PATH"), &html_escape($real));
        print &ui_table_row(L("COL_TYPE"), L("VALUE_FILE"));
        print &ui_table_row(L("COL_SIZE"), &html_escape($size));
        print &ui_table_row(L("COL_PERMISSIONS"), &html_escape($perm));
        print &ui_table_row(L("COL_MODIFIED"), &html_escape($mtime));
        print &ui_table_end();

        my ($preview, $trunc, $binary, $perr) = $file_preview->($real, $preview_lines, 131072);
        print &ui_subheading(L("SUB_FILE_PREVIEW"));
        if ($perr) {
            print &ui_alert(L("ERR_BROWSE_LIST_FAILED", $perr), "warning");
        } elsif ($binary) {
            print &ui_alert(L("MSG_FILE_PREVIEW_BINARY"), "info");
        } else {
            print "<pre class='zfsguru-code-block'>" . &html_escape($preview || '') . "</pre>";
            print "<p class='zfsguru-muted'>" . L("MSG_FILE_PREVIEW_TRUNCATED") . "</p>" if $trunc;
        }
        return;
    }

    opendir my $dh, $real or do {
        print &ui_print_error(L("ERR_BROWSE_LIST_FAILED", $!));
        return;
    };
    my @names = readdir $dh;
    closedir $dh;

    my @entries;
    for my $name (@names) {
        next if $name eq '.' || $name eq '..';
        next if !$show_hidden && $name =~ /^\./;

        my $child = ($real eq '/') ? "/$name" : "$real/$name";
        my @lst = lstat($child);
        my $perm = @lst ? sprintf("%04o", ($lst[2] & 07777)) : '-';
        my $mtime = @lst ? scalar(localtime($lst[9] || 0)) : '-';

        my $is_link = -l $child ? 1 : 0;
        my $is_dir  = -d $child ? 1 : 0;
        my $is_file = -f $child ? 1 : 0;

        my $type = $is_dir ? L("VALUE_DIRECTORY")
                 : $is_link ? L("VALUE_SYMLINK")
                 : $is_file ? L("VALUE_FILE")
                 : L("VALUE_OTHER");

        my $size = $is_file && @lst ? $human_size->($lst[7] || 0) : '-';
        my $href = "files.cgi?action=browse&path=" . &url_encode($child) .
                   "&show_hidden=" . ($show_hidden ? 1 : 0) .
                   "&preview_lines=" . $preview_lines;
        my $name_html = "<a href='" . &html_escape($href) . "'>" . &html_escape($name) . "</a>";

        if ($is_link) {
            my $tgt = readlink($child);
            if (defined $tgt && length $tgt) {
                $name_html .= " <span class='zfsguru-muted'>&rarr; " . &html_escape($tgt) . "</span>";
            }
        }

        push @entries, {
            is_dir => $is_dir,
            name => $name,
            row => [ $name_html, $type, $size, $perm, $mtime ],
        };
    }

    @entries = sort {
        ($b->{is_dir} <=> $a->{is_dir}) ||
        (lc($a->{name}) cmp lc($b->{name}))
    } @entries;

    my @heads = (
        L("COL_NAME"),
        L("COL_TYPE"),
        L("COL_SIZE"),
        L("COL_PERMISSIONS"),
        L("COL_MODIFIED"),
    );
    my @rows = map { $_->{row} } @entries;
    print &ui_columns_table(\@heads, 100, \@rows, undef, 1,
        L("TABLE_BROWSE_ENTRIES"), L("VALUE_NONE"));
}

sub action_snapshots {
    print &ui_subheading(L("SUB_SNAPSHOTS"));
    print "<p>" . L("MSG_SNAPSHOTS_HELP") . "</p>";

    my $dataset = $in{'dataset'} || '';
    my $sort = $in{'sort'} || '';
    my $invert = $in{'invert'} ? 1 : 0;
    my $datasets = zfs_list([qw(name type mountpoint)], '-t', 'filesystem,volume');
    my %ds_type = map { $_->{name} => $_->{type} } @$datasets;
    my %ds_mount = map { $_->{name} => $_->{mountpoint} } @$datasets;
    my @opts = map { [ $_->{name}, $_->{name} . " (" . $_->{type} . ")" ] }
               sort { $a->{name} cmp $b->{name} } @$datasets;
    unshift @opts, [ '', L("VALUE_ALL_SNAPSHOTS") ];

    my $global_mode = $dataset ? 0 : 1;

    my %sort_ok_global = map { $_ => 1 } qw(fs name used refer creation);
    my %sort_ok_dataset = map { $_ => 1 } qw(name used refer creation);
    if ($global_mode) {
        $sort = 'creation' if !$sort || !$sort_ok_global{$sort};
    } else {
        $sort = 'creation' if !$sort || !$sort_ok_dataset{$sort};
    }

    my $size_to_bytes = sub {
        my ($val) = @_;
        return 0 unless defined $val;
        $val =~ s/^\s+|\s+$//g;
        return 0 if $val eq '' || $val eq '-';
        return $val + 0 if $val =~ /^\d+$/;
        if ($val =~ /^(\d+(?:\.\d+)?)([KMGTPZE])B?$/i) {
            my ($num, $unit) = ($1, uc($2));
            my %pow = (K => 1, M => 2, G => 3, T => 4, P => 5, Z => 6, E => 7);
            my $base = 1024;
            return $num * ($base ** $pow{$unit});
        }
        if ($val =~ /^(\d+(?:\.\d+)?)B$/i) {
            return $1 + 0;
        }
        return 0;
    };

    my $creation_to_epoch = sub {
        my ($val) = @_;
        return 0 unless defined $val;
        $val =~ s/^\s+|\s+$//g;
        return 0 if $val eq '' || $val eq '-';
        return int($val) if $val =~ /^\d+$/;
        my $epoch = 0;
        eval {
            require Time::Piece;
            my $t = Time::Piece->strptime($val, "%a %b %e %H:%M %Y");
            $epoch = $t->epoch if $t;
        };
        return $epoch;
    };

    my $sort_link = sub {
        my ($col, $label) = @_;
        my $new_invert = ($sort eq $col) ? ($invert ? 0 : 1) : 0;
        my $url = "files.cgi?action=snapshots";
        $url .= "&dataset=" . &url_encode($dataset) if length $dataset;
        $url .= "&sort=" . &url_encode($col) . "&invert=" . ($new_invert ? 1 : 0);
        my $arrow = '';
        if ($sort eq $col) {
            $arrow = $invert ? ' &darr;' : ' &uarr;';
        }
        return "<a href='" . &html_escape($url) . "'>" . &html_escape($label) . "</a>" . $arrow;
    };

    print &ui_form_start("files.cgi", "get");
    print &ui_hidden("action", "snapshots");
    print &ui_hidden("sort", $sort);
    print &ui_hidden("invert", $invert ? 1 : 0);
    print &ui_table_start(L("TABLE_SNAPSHOT_FILTER"), "width=100%", 2);
    print &ui_table_row(L("ROW_DATASET_NAME"), &ui_select("dataset", $dataset, \@opts));
    print &ui_table_end();
    print &ui_form_end([ [ "apply", L("BTN_VIEW") ] ]);

    if (!$global_mode) {
        if (!is_dataset_name($dataset) || !exists $ds_type{$dataset}) {
            print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
            return;
        }

        if ($in{'snapdir_show'} || $in{'snapdir_hide'}) {
            if ($ds_type{$dataset} ne 'filesystem') {
                print &ui_print_error(L("ERR_SNAPDIR_ONLY_FILESYSTEM"));
            } else {
                my $val = $in{'snapdir_show'} ? 'visible' : 'hidden';
                eval {
                    zfs_set($dataset, { snapdir => $val });
                    log_info("Set snapdir=$val on $dataset");
                    print &ui_print_success(L("SUCCESS_SNAPDIR_UPDATED", $dataset, $val));
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SNAPDIR_UPDATE_FAILED", $@));
                }
            }
        }

        if ($in{'snapshot_create'}) {
            my $snapname = $in{'snapshot_name'} || '';
            $snapname =~ s/^\s+|\s+$//g;
            if (!$snapname || $snapname =~ /\@/) {
                print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
            } else {
                eval {
                    my $full_snapshot = "$dataset\@$snapname";
                    zfs_snapshot($full_snapshot);
                    log_info("Created snapshot $dataset\@$snapname");
                    print &ui_print_success(L("SUCCESS_SNAPSHOT_CREATED"));
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SNAPSHOT_CREATE_FAILED", $@));
                }
            }
        }
    }

    my $snapshots = $global_mode ? zfs_list_snapshots_all() : zfs_list_snapshots($dataset);
    my %snap_ok = map { ($_->{name} || '') => 1 } @$snapshots;
    my $snapshots_changed = 0;

    if ($in{'snapshot_rollback'} || $in{'snapshot_clone'} || $in{'snapshot_destroy'}) {
        my $snap = $in{'snapshot_selected'} || '';

        my $in_scope = 0;
        if ($global_mode) {
            $in_scope = is_snapshot_fullname($snap) && $snap_ok{$snap};
        } else {
            my $prefix_exact = "$dataset\@";
            my $prefix_child = "$dataset/";
            $in_scope = is_snapshot_fullname($snap) && $snap_ok{$snap} &&
                        (index($snap, $prefix_exact) == 0 || index($snap, $prefix_child) == 0);
        }

        if (!$in_scope) {
            print &ui_print_error(L("ERR_SNAPSHOT_SELECT_ONE"));
        } elsif ($in{'snapshot_rollback'}) {
            my %opt = ();
            if ($advanced_enabled) {
                $opt{destroy_newer} = $in{'rollback_destroy_newer'} ? 1 : 0;
                $opt{destroy_clones} = $in{'rollback_destroy_clones'} ? 1 : 0;
                $opt{force} = $in{'rollback_force'} ? 1 : 0;
            }

            if (!$in{'confirm_snapshot_rollback'}) {
                print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_ROLLBACK_REQUIRED"));
                print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_WARNING"), "warning");
            } elsif ($opt{destroy_clones} && !$in{'confirm_snapshot_rollback_clones'}) {
                print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_ROLLBACK_CLONES_REQUIRED"));
                print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_CLONES_WARNING"), "warning");
            } else {
                eval {
                    zfs_rollback($snap, \%opt);
                    log_info("Rolled back to snapshot $snap");
                    print &ui_print_success(L("SUCCESS_SNAPSHOT_ROLLBACK", $snap));
                    $snapshots_changed = 1;
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SNAPSHOT_ROLLBACK_FAILED", $@));
                }
            }
        } elsif ($in{'snapshot_destroy'}) {
            if (!$in{'confirm_snapshot_destroy'}) {
                print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_DESTROY_REQUIRED"));
                print &ui_alert(L("MSG_SNAPSHOT_DESTROY_WARNING"), "warning");
            } else {
                eval {
                    zfs_destroy_snapshot($snap, 0);
                    log_info("Destroyed snapshot $snap");
                    print &ui_print_success(L("SUCCESS_SNAPSHOT_DELETED"));
                    $snapshots_changed = 1;
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SNAPSHOT_DELETE_FAILED", $@));
                }
            }
        } elsif ($in{'snapshot_clone'}) {
            my $target = $in{'clone_target_dataset'} || '';
            $target =~ s/^\s+|\s+$//g;
            my $promote = $in{'clone_promote'} ? 1 : 0;
            if (!is_dataset_name($target)) {
                print &ui_print_error(L("ERR_CLONE_TARGET_INVALID", $target));
            } else {
                eval {
                    zfs_clone($snap, $target);
                    log_info("Cloned snapshot $snap -> $target");
                    if ($promote) {
                        zfs_promote($target);
                        log_info("Promoted clone $target");
                    }
                    print &ui_print_success(L("SUCCESS_SNAPSHOT_CLONED", $target));
                    $snapshots_changed = 1;
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SNAPSHOT_CLONE_FAILED", $@));
                }
            }
        }
    }

    if ($snapshots_changed) {
        $snapshots = $global_mode ? zfs_list_snapshots_all() : zfs_list_snapshots($dataset);
        %snap_ok = map { ($_->{name} || '') => 1 } @$snapshots;
    }

    if (!$global_mode) {
        print "<p><a class='button' href='advanced_datasets.cgi?action=snapshots&dataset=" .
              &url_encode($dataset) . "'>" . L("BTN_MANAGE_SNAPSHOTS") . "</a></p>";

        if ($ds_type{$dataset} eq 'filesystem') {
            my $snapdir = zfs_get_prop_value($dataset, 'snapdir') || 'hidden';
            print &ui_subheading(L("SUB_SNAPSHOT_VISIBILITY"));
            print &ui_form_start("files.cgi", "post");
            print &ui_hidden("action", "snapshots");
            print &ui_hidden("dataset", $dataset);
            print &ui_hidden("sort", $sort);
            print &ui_hidden("invert", $invert ? 1 : 0);
            print &ui_table_start(L("TABLE_SNAPSHOT_VISIBILITY"), "width=100%", 2);
            print &ui_table_row(L("ROW_SNAPDIR_STATUS"), &html_escape($snapdir));
            print &ui_table_end();
            print &ui_form_end([
                [ "snapdir_show", L("BTN_SNAPDIR_SHOW") ],
                [ "snapdir_hide", L("BTN_SNAPDIR_HIDE") ],
            ]);
        }

        print &ui_hr();
        print &ui_subheading(L("SUB_SNAPSHOT_CREATE"));
        print &ui_form_start("files.cgi", "post");
        print &ui_hidden("action", "snapshots");
        print &ui_hidden("dataset", $dataset);
        print &ui_hidden("sort", $sort);
        print &ui_hidden("invert", $invert ? 1 : 0);
        print &ui_hidden("snapshot_create", 1);
        print &ui_table_start(L("TABLE_CREATE_SNAPSHOT"), "width=100%", 2);
        print &ui_table_row(L("ROW_SNAPSHOT_NAME"), &ui_textbox("snapshot_name", "", 30) .
            "<br><small>" . L("HINT_SNAPSHOT_NAME") . "</small>");
        print &ui_table_end();
        print &ui_form_end([ [ "snapshot_create", L("BTN_CREATE_SNAPSHOT") ] ]);
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_SNAPSHOT_OPERATIONS"));
    print &ui_alert(L("MSG_SNAPSHOT_OPERATIONS_WARNING"), "warning");

    print &ui_form_start("files.cgi", "post");
    print &ui_hidden("action", "snapshots");
    print &ui_hidden("dataset", $dataset);
    print &ui_hidden("sort", $sort);
    print &ui_hidden("invert", $invert ? 1 : 0);
    my $picked = $in{'snapshot_selected'} || '';

    my @rows = ();
    if (@$snapshots) {
        for my $snap (@$snapshots) {
            my $full = $snap->{name} || '';
            next unless $full;

            my ($fs, $sn) = split(/\@/, $full, 2);
            $sn = '' unless defined $sn;

            my $disp = $sn;
            if (!$global_mode) {
                $disp = $full;
                if (index($full, "$dataset\@") == 0) {
                    $disp = $sn;
                } elsif (index($full, "$dataset/") == 0) {
                    $disp = $full;
                    $disp =~ s/^\Q$dataset\E\///;
                }
            }

            push @rows, {
                name     => $full,
                fs       => $fs,
                snap     => $sn,
                display  => $disp,
                used     => $snap->{used},
                used_b   => $size_to_bytes->($snap->{used}),
                refer    => $snap->{refer},
                refer_b  => $size_to_bytes->($snap->{refer}),
                creation => $snap->{creation},
                creation_epoch => $creation_to_epoch->($snap->{creation}),
            };
        }
    }

    my $sort_cmp = sub {
        my ($a, $b) = @_;
        my $res = 0;
        if ($global_mode && $sort eq 'fs') {
            $res = ($a->{fs} cmp $b->{fs}) || ($a->{snap} cmp $b->{snap});
        } elsif ($sort eq 'name') {
            $res = $global_mode ? ($a->{snap} cmp $b->{snap}) : (($a->{display} || '') cmp ($b->{display} || ''));
        } elsif ($sort eq 'used') {
            $res = ($a->{used_b} || 0) <=> ($b->{used_b} || 0);
        } elsif ($sort eq 'refer') {
            $res = ($a->{refer_b} || 0) <=> ($b->{refer_b} || 0);
        } elsif ($sort eq 'creation') {
            $res = ($a->{creation_epoch} || 0) <=> ($b->{creation_epoch} || 0);
            $res = ($a->{creation} cmp $b->{creation}) if $res == 0;
        }
        $res = ($a->{name} cmp $b->{name}) if $res == 0;
        return $invert ? -$res : $res;
    };
    @rows = sort { $sort_cmp->($a, $b) } @rows;

    my @headers = (L("COL_SELECT"));
    if ($global_mode) {
        push @headers,
            $sort_link->('fs', L("COL_FILESYSTEM")),
            $sort_link->('name', L("COL_SNAPSHOT")),
            $sort_link->('used', L("COL_USED")),
            $sort_link->('refer', L("COL_REFERENCED")),
            $sort_link->('creation', L("COL_CREATION_DATE"));
    } else {
        push @headers,
            $sort_link->('name', L("COL_SNAPSHOT")),
            $sort_link->('used', L("COL_USED")),
            $sort_link->('refer', L("COL_REFERENCED")),
            $sort_link->('creation', L("COL_CREATION_DATE"));
    }

    my @snap_data;
    for my $row (@rows) {
        my $full = $row->{name} || '';
        next unless $full;

        if ($global_mode) {
            my $fs = $row->{fs} || '-';
            my $snapname = $row->{snap} || '-';
            my $fs_url_sort = ($sort eq 'fs') ? 'name' : $sort;
            my $fs_url = "files.cgi?action=snapshots&dataset=" . &url_encode($fs) .
                         "&sort=" . &url_encode($fs_url_sort) . "&invert=" . ($invert ? 1 : 0);
            push @snap_data, [
                { type => 'radio', name => 'snapshot_selected', value => $full, checked => ($picked eq $full ? 1 : 0) },
                "<a href='" . &html_escape($fs_url) . "'>" . &html_escape($fs) . "</a>",
                &html_escape($snapname),
                &html_escape($row->{used} || '-'),
                &html_escape($row->{refer} || '-'),
                &html_escape($row->{creation} || '-'),
            ];
        } else {
            push @snap_data, [
                { type => 'radio', name => 'snapshot_selected', value => $full, checked => ($picked eq $full ? 1 : 0) },
                &html_escape($row->{display} || $full || '-'),
                &html_escape($row->{used} || '-'),
                &html_escape($row->{refer} || '-'),
                &html_escape($row->{creation} || '-'),
            ];
        }
    }

    print &ui_columns_table(\@headers, 100, \@snap_data, undef, 1,
        L("TABLE_SNAPSHOTS"), L("ERR_NO_SNAPSHOTS_FOUND"));

    print &ui_table_start(L("TABLE_SNAPSHOT_ACTIONS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_ROLLBACK"),
        &ui_checkbox("confirm_snapshot_rollback", 1, L("LBL_CONFIRM_SNAPSHOT_ROLLBACK"), 0));
    if ($advanced_enabled) {
        my $opts = join("<br>",
            &ui_checkbox("rollback_destroy_newer", 1, L("LBL_ROLLBACK_DESTROY_NEWER"), 0),
            &ui_checkbox("rollback_destroy_clones", 1, L("LBL_ROLLBACK_DESTROY_CLONES"), 0),
            &ui_checkbox("rollback_force", 1, L("LBL_ROLLBACK_FORCE"), 0),
        );
        print &ui_table_row(L("ROW_ROLLBACK_OPTIONS"), $opts);
        print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_ROLLBACK_CLONES"),
            &ui_checkbox("confirm_snapshot_rollback_clones", 1, L("LBL_CONFIRM_SNAPSHOT_ROLLBACK_CLONES"), 0));
    }
    print &ui_table_row(L("ROW_CLONE_TARGET_DATASET"),
        &ui_textbox("clone_target_dataset", "", 40) . "<br><small>" . L("HINT_CLONE_TARGET_DATASET") . "</small>");
    print &ui_table_row(L("ROW_CLONE_PROMOTE"),
        &ui_checkbox("clone_promote", 1, L("LBL_CLONE_PROMOTE"), 0));
    print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_DESTROY"),
        &ui_checkbox("confirm_snapshot_destroy", 1, L("LBL_CONFIRM_SNAPSHOT_DESTROY"), 0));
    print &ui_table_end();

    print &ui_form_end([
        [ "snapshot_rollback", L("BTN_ROLLBACK") ],
        [ "snapshot_clone", L("BTN_CLONE") ],
        [ "snapshot_destroy", L("BTN_DELETE_SNAPSHOT") ],
    ]);
}

sub action_volumes {
    print &ui_subheading(L("SUB_VOLUMES"));

    my $spa = zfs_version();
    my $sync_supported = (defined $spa && $spa =~ /^\d+$/ && $spa >= 28) ? 1 : 0;

    my $normalize_size = sub {
        my ($val) = @_;
        return '' unless defined $val;
        $val =~ s/^\s+|\s+$//g;
        return '' unless length $val;
        if ($val =~ /^\d+(?:\.\d+)?$/) {
            $val .= "G";
        }
        return $val;
    };

    my $iscsi_target_for = sub {
        my ($zvol) = @_;
        return '' unless defined $zvol && length $zvol;
        my $prefix = "iqn." . strftime("%Y-%m", localtime()) . ".zfsguru";
        my $name = $zvol;
        $name =~ s{[^A-Za-z0-9_.\-]+}{.}g;
        $name =~ s/^\.+//;
        $name =~ s/\.+$//;
        return $prefix . ":" . $name;
    };

    my $CTL_CONF = '/etc/ctl.conf';
    my $ctl_raw = read_file_text($CTL_CONF);
    my $iscsi_target_exists = sub {
        my ($target_name) = @_;
        return 0 unless defined $target_name && length $target_name;
        return ($ctl_raw =~ /^\s*target\s+\Q$target_name\E\s*\{/m) ? 1 : 0;
    };

    my $size_to_bytes = sub {
        my ($val) = @_;
        return 0 unless defined $val && length $val;
        $val =~ s/^\s+|\s+$//g;
        if ($val =~ /^\d+$/) {
            return $val + 0;
        }
        if ($val =~ /^(\d+(?:\.\d+)?)([KMGTP])([iI]?)B?$/i) {
            my ($num, $unit, $i) = ($1, uc($2), $3);
            my %pow = (K => 1, M => 2, G => 3, T => 4, P => 5);
            my $base = 1024;
            return $num * ($base ** $pow{$unit});
        }
        return 0;
    };

    if ($in{'create_volume'}) {
        my $parent = $in{'volume_parent'} || '';
        my $name = $in{'volume_name'} || '';
        my $size = $normalize_size->($in{'volume_size'} || '');
        my $block = $in{'volume_blocksize'} || '';
        my $sync = $in{'volume_sync'} || '';
        my $swap = $in{'volume_swap'} ? 1 : 0;
        my $sparse = $in{'volume_sparse'} ? 1 : 0;

        my $dataset = $name;
        if ($parent && $name && $name !~ m{/}) {
            $dataset = "$parent/$name";
        }

        if (!is_dataset_name($dataset)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $dataset));
        } elsif (!is_zfs_size($size)) {
            print &ui_print_error(L("ERR_VOLUME_SIZE_INVALID", $size));
        } elsif ($block && !is_zfs_size($block)) {
            print &ui_print_error(L("ERR_VOLUME_SIZE_INVALID", $block));
        } elsif ($sync && !$sync_supported) {
            print &ui_print_error(L("ERR_SYNC_NOT_SUPPORTED"));
        } else {
            eval {
                my %props;
                $props{volblocksize} = $block if $block;
                if ($sync_supported && $sync) {
                    die "Invalid sync value" unless $sync =~ /^(standard|always|disabled)$/;
                    $props{sync} = $sync;
                }
                if ($swap) {
                    $props{'org.freebsd:swap'} = 'on';
                }
                zfs_create_volume($dataset, $size, \%props, $sparse);
                if ($swap) {
                    swap_on($dataset);
                }
                log_info("Created zvol $dataset size=$size");
                print &ui_print_success(L("SUCCESS_VOLUME_CREATED", $dataset));
            };
            if ($@) {
                print &ui_print_error(L("ERR_VOLUME_CREATE_FAILED", $@));
            }
        }
    }

    my $selected = $in{'manage_volume'} || '';

    if ($in{'resize_volume'}) {
        my $name = $selected;
        my $size = $normalize_size->($in{'new_volume_size'} || '');
        my $is_shrink = 0;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!is_zfs_size($size)) {
            print &ui_print_error(L("ERR_VOLUME_SIZE_INVALID", $size));
        } elsif (!$in{'confirm_resize'}) {
            print &ui_print_error(L("ERR_CONFIRM_VOLUME_RESIZE_REQUIRED"));
        } else {
            my $cur = zfs_get_prop_value_bytes($name, 'volsize');
            if ($cur && $size && $cur =~ /^\d+$/ && $size =~ /^\d+$/) {
                $is_shrink = ($size < $cur) ? 1 : 0;
            } elsif ($cur && $size && $cur =~ /^\d+$/ && $size !~ /^\d+$/) {
                my $s_bytes = $size_to_bytes->($size);
                $is_shrink = ($s_bytes && $s_bytes < $cur) ? 1 : 0;
            }
            if ($is_shrink && !$in{'confirm_shrink'}) {
                print &ui_print_error(L("ERR_CONFIRM_SHRINK_REQUIRED"));
                print &ui_alert(L("MSG_SHRINK_WARNING"), "warning");
            } else {
                eval {
                    zfs_resize_volume($name, $size);
                    log_info("Resized zvol $name to $size");
                    print &ui_print_success(L("SUCCESS_VOLUME_RESIZED", $name));
                };
                if ($@) {
                    print &ui_print_error(L("ERR_VOLUME_RESIZE_FAILED", $@));
                }
            }
        }
    }

    if ($in{'destroy_volume'}) {
        my $name = $selected;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!$in{'confirm_destroy'}) {
            print &ui_print_error(L("ERR_CONFIRM_VOLUME_DESTROY_REQUIRED"));
        } else {
            eval {
                if (swap_is_active($name)) {
                    swap_off($name);
                }
                zfs_destroy($name);
                log_info("Destroyed zvol $name");
                print &ui_print_success(L("SUCCESS_VOLUME_DESTROYED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_VOLUME_DESTROY_FAILED", $@));
            }
        }
    }

    if ($in{'enable_swap'}) {
        my $name = $selected;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!$in{'confirm_swap_enable'}) {
            print &ui_print_error(L("ERR_CONFIRM_SWAP_ENABLE_REQUIRED"));
        } else {
            eval {
                zfs_set($name, { 'org.freebsd:swap' => 'on' });
                swap_on($name);
                log_info("Enabled swap on zvol $name");
                print &ui_print_success(L("SUCCESS_SWAP_ENABLED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SWAP_ENABLE_FAILED", $@));
            }
        }
    }

    if ($in{'activate_swap'}) {
        my $name = $selected;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } else {
            eval {
                swap_on($name);
                log_info("Activated swap on zvol $name");
                print &ui_print_success(L("SUCCESS_SWAP_ACTIVATED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SWAP_ENABLE_FAILED", $@));
            }
        }
    }

    if ($in{'disable_swap'}) {
        my $name = $selected;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } else {
            eval {
                if (swap_is_active($name)) {
                    swap_off($name);
                }
                zfs_set($name, { 'org.freebsd:swap' => 'off' });
                log_info("Disabled swap on zvol $name");
                print &ui_print_success(L("SUCCESS_SWAP_DISABLED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SWAP_DISABLE_FAILED", $@));
            }
        }
    }

    if ($in{'sync_disable'} || $in{'sync_enable'}) {
        my $name = $selected;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!$sync_supported) {
            print &ui_print_error(L("ERR_SYNC_NOT_SUPPORTED"));
        } else {
            my $val = $in{'sync_disable'} ? 'disabled' : 'standard';
            eval {
                zfs_set($name, { sync => $val });
                log_info("Set sync=$val on zvol $name");
                print &ui_print_success(L("SUCCESS_SYNC_UPDATED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SYNC_UPDATE_FAILED", $@));
            }
        }
    }

    if ($in{'update_zvol_tuning'} || $in{'update_sync'}) {
        my $name = $selected;
        my $sync_val = $in{'volume_sync_update'} || '';
        my $copies_val = $in{'volume_copies_update'} || '';

        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } else {
            my %set;
            my $have_error = 0;
            if ($sync_supported && length $sync_val) {
                if ($sync_val !~ /^(standard|always|disabled)$/) {
                    print &ui_print_error(L("ERR_SYNC_UPDATE_FAILED", "Invalid sync value"));
                    $have_error = 1;
                } else {
                    $set{sync} = $sync_val;
                }
            } elsif ($in{'update_sync'} && !$sync_supported) {
                # Backwards compatible behavior when old Save Sync handler is triggered.
                print &ui_print_error(L("ERR_SYNC_NOT_SUPPORTED"));
                $have_error = 1;
            }

            if (length $copies_val) {
                if ($copies_val !~ /^[123]$/) {
                    print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", "copies", $copies_val));
                    $have_error = 1;
                } else {
                    $set{copies} = $copies_val;
                }
            }

            if (!$have_error && !%set) {
                print &ui_print_error(L("ERR_ZVOL_TUNING_NO_CHANGES"));
            }

            if (!$have_error && %set) {
                eval {
                    zfs_set($name, \%set);
                    log_info("Updated zvol tuning for $name: " . join(', ', map { "$_=$set{$_}" } sort keys %set));
                    print &ui_print_success(L("SUCCESS_ZVOL_TUNING_UPDATED", $name));
                };
                if ($@) {
                    print &ui_print_error(L("ERR_ZVOL_TUNING_UPDATE_FAILED", $@));
                }
            }
        }
    }

    if ($in{'provision_full'} || $in{'provision_thin'}) {
        my $name = $selected;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } else {
            eval {
                if ($in{'provision_full'}) {
                    my $volsize = zfs_get_prop_value($name, 'volsize');
                    die L("ERR_VOLSIZE_READ_FAILED", $name) unless $volsize;
                    zfs_set($name, { refreservation => $volsize });
                    log_info("Set full provisioning on zvol $name");
                    print &ui_print_success(L("SUCCESS_PROVISION_FULL", $name));
                } else {
                    zfs_set($name, { refreservation => 'none' });
                    log_info("Set thin provisioning on zvol $name");
                    print &ui_print_success(L("SUCCESS_PROVISION_THIN", $name));
                }
            };
            if ($@) {
                print &ui_print_error(L("ERR_PROVISIONING_FAILED", $@));
            }
        }
    }

    if ($in{'create_zvol_snapshot'}) {
        my $name = $selected;
        my $snapname = $in{'zvol_snapshot_name'} || '';
        $snapname =~ s/^\s+|\s+$//g;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!$snapname || $snapname =~ /\@/) {
            print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
        } else {
            eval {
                my $full_snapshot = "$name\@$snapname";
                zfs_snapshot($full_snapshot);
                log_info("Created snapshot $name\@$snapname");
                print &ui_print_success(L("SUCCESS_ZVOL_SNAPSHOT_CREATED", $name, $snapname));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SNAPSHOT_CREATE_FAILED", $@));
            }
        }
    }

    if ($in{'destroy_zvol_snapshot'}) {
        my $name = $selected;
        my $snap = $in{'zvol_snapshot_delete'} || '';
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!$snap || $snap !~ /\@/ || $snap !~ /^\Q$name\E\@/) {
            print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
        } elsif (!$in{'confirm_snapshot_destroy'}) {
            print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_DESTROY_REQUIRED"));
        } else {
            eval {
                zfs_destroy_snapshot($snap, 0);
                log_info("Destroyed snapshot $snap");
                print &ui_print_success(L("SUCCESS_ZVOL_SNAPSHOT_DELETED", $snap));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SNAPSHOT_DELETE_FAILED", $@));
            }
        }
    }

    if ($in{'rollback_zvol_snapshot'}) {
        my $name = $selected;
        my $snap = $in{'zvol_snapshot_rollback'} || '';
        my %opt = ();
        if ($advanced_enabled) {
            $opt{destroy_newer} = $in{'rollback_destroy_newer'} ? 1 : 0;
            $opt{destroy_clones} = $in{'rollback_destroy_clones'} ? 1 : 0;
            $opt{force} = $in{'rollback_force'} ? 1 : 0;
        }
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!is_snapshot_fullname($snap) || index($snap, "$name\@") != 0) {
            print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
        } elsif (!$in{'confirm_snapshot_rollback'}) {
            print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_ROLLBACK_REQUIRED"));
            print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_WARNING"), "warning");
        } elsif ($opt{destroy_clones} && !$in{'confirm_snapshot_rollback_clones'}) {
            print &ui_print_error(L("ERR_CONFIRM_SNAPSHOT_ROLLBACK_CLONES_REQUIRED"));
            print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_CLONES_WARNING"), "warning");
        } else {
            eval {
                zfs_rollback($snap, \%opt);
                log_info("Rolled back zvol $name to snapshot $snap");
                print &ui_print_success(L("SUCCESS_SNAPSHOT_ROLLBACK", $snap));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SNAPSHOT_ROLLBACK_FAILED", $@));
            }
        }
    }

    if ($in{'clone_zvol_snapshot'}) {
        my $name = $selected;
        my $snap = $in{'zvol_snapshot_clone'} || '';
        my $target = $in{'clone_target_dataset'} || '';
        $target =~ s/^\s+|\s+$//g;
        my $promote = $in{'clone_promote'} ? 1 : 0;
        if (!is_dataset_name($name)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $name));
        } elsif (!is_snapshot_fullname($snap) || index($snap, "$name\@") != 0) {
            print &ui_print_error(L("ERR_SNAPSHOT_NAME_REQUIRED"));
        } elsif (!is_dataset_name($target)) {
            print &ui_print_error(L("ERR_CLONE_TARGET_INVALID", $target));
        } else {
            eval {
                zfs_clone($snap, $target);
                log_info("Cloned zvol snapshot $snap -> $target");
                if ($promote) {
                    zfs_promote($target);
                    log_info("Promoted clone $target");
                }
                print &ui_print_success(L("SUCCESS_SNAPSHOT_CLONED", $target));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SNAPSHOT_CLONE_FAILED", $@));
            }
        }
    }

    my $vols = zfs_list([qw(name used avail refer volsize volblocksize)], '-t', 'volume');
    my %volinfo;
    for my $v (@$vols) {
        my $din = diskinfo("zvol/$v->{name}");
        my $sector = $din ? $din->{sectorsize} : undef;
        my $refres = zfs_get_prop_value($v->{name}, 'refreservation');
        my $swap = zfs_get_prop_value($v->{name}, 'org.freebsd:swap');
        my $sync = $sync_supported ? zfs_get_prop_value($v->{name}, 'sync') : undef;
        my $copies = zfs_get_prop_value($v->{name}, 'copies');
        my $prov = 'thin';
        if (defined $refres) {
            my $r = lc($refres);
            $prov = ($r eq 'none' || $r =~ /^0/) ? 'thin' : 'full';
        }
        my $swap_on = (defined $swap && $swap eq 'on') ? 1 : 0;
        my $swap_active = $swap_on ? swap_is_active($v->{name}) : 0;
        $volinfo{$v->{name}} = {
            %$v,
            provisioning => $prov,
            swap_on      => $swap_on,
            swap_active  => $swap_active,
            sync         => $sync,
            sector_size  => $sector,
            copies       => $copies,
        };
    }

    my $fslist = zfs_list([qw(name)], '-t', 'filesystem');
    my @fs_opts = map { [ $_->{name}, $_->{name} ] } @$fslist;
    unshift @fs_opts, [ '', L("VALUE_NONE") ];

    my @block_opts = (
        [ '512',  '512' ],
        [ '4K',   '4K' ],
        [ '8K',   '8K' ],
        [ '16K',  '16K' ],
        [ '32K',  '32K' ],
        [ '64K',  '64K' ],
        [ '128K', '128K' ],
    );

    print &ui_subheading(L("SUB_VOLUME_CREATE"));
    print &ui_form_start("files.cgi", "post");
    print &ui_hidden("action", "volumes");
    if ($selected) {
        print &ui_hidden("manage_volume", $selected);
    }
    print &ui_hidden("create_volume", 1);
    print &ui_table_start(L("TABLE_VOLUME_CREATE"), "width=100%", 2);
    print &ui_table_row(L("ROW_VOLUME_PARENT"), &ui_select("volume_parent", "", \@fs_opts));
    print &ui_table_row(L("ROW_VOLUME_NAME"), &ui_textbox("volume_name", "", 40));
    print &ui_table_row(L("ROW_VOLUME_SIZE"), &ui_textbox("volume_size", "10", 12) . " " . L("HINT_VOLUME_SIZE"));
    print &ui_table_row(L("ROW_VOLBLOCKSIZE"), &ui_select("volume_blocksize", "64K", \@block_opts) . " " . L("HINT_VOLBLOCKSIZE"));
    if ($sync_supported) {
        print &ui_table_row(L("ROW_VOLUME_SYNC"), &ui_select("volume_sync", "standard", [
            [ "standard", L("OPT_SYNC_STANDARD") ],
            [ "always", L("OPT_SYNC_ALWAYS") ],
            [ "disabled", L("OPT_SYNC_DISABLED") ],
        ]));
    }
    print &ui_table_row(L("ROW_VOLUME_SWAP"), &ui_checkbox("volume_swap", 1, L("HINT_VOLUME_SWAP"), 0));
    print &ui_table_row(L("ROW_VOLUME_SPARSE"), &ui_checkbox("volume_sparse", 1, L("HINT_VOLUME_SPARSE"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "create_volume", L("BTN_CREATE_VOLUME") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_VOLUME_MANAGE"));
    print &ui_form_start("files.cgi", "post");
    print &ui_hidden("action", "volumes");
    my @opts = map { [ $_->{name}, $_->{name} ] } @$vols;
    print &ui_table_start(L("TABLE_VOLUME_MANAGE"), "width=100%", 2);
    print &ui_table_row(L("ROW_SELECT_VOLUME"), &ui_select("manage_volume", $selected, \@opts));
    print &ui_table_row(L("ROW_NEW_VOLUME_SIZE"), &ui_textbox("new_volume_size", "", 12) . " " . L("HINT_VOLUME_SIZE"));
    print &ui_table_row(L("ROW_CONFIRM_RESIZE"), &ui_checkbox("confirm_resize", 1, L("LBL_CONFIRM_RESIZE"), 0));
    print &ui_table_row(L("ROW_CONFIRM_SHRINK"), &ui_checkbox("confirm_shrink", 1, L("LBL_CONFIRM_SHRINK"), 0));
    print &ui_table_row(L("ROW_CONFIRM_DESTROY"), &ui_checkbox("confirm_destroy", 1, L("LBL_CONFIRM_DESTROY"), 0));
    if ($selected && $volinfo{$selected} && !$volinfo{$selected}{swap_on}) {
        print &ui_table_row(L("ROW_CONFIRM_SWAP_ENABLE"),
            &ui_checkbox("confirm_swap_enable", 1, L("LBL_CONFIRM_SWAP_ENABLE"), 0));
    }
    print &ui_table_end();

    my $selected_info = ($selected && $volinfo{$selected}) ? $volinfo{$selected} : undef;
    if ($selected_info) {
        my $swap_text = $selected_info->{swap_on} ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
        if ($selected_info->{swap_on}) {
            $swap_text .= $selected_info->{swap_active} ? " (" . L("VALUE_ACTIVE") . ")" : " (" . L("VALUE_INACTIVE") . ")";
        }
        my $sync_text = defined $selected_info->{sync} ? $selected_info->{sync} : L("VALUE_UNKNOWN");
        my $prov_text = $selected_info->{provisioning} eq 'full' ? L("VALUE_FULL") : L("VALUE_THIN");
        my $sector_disp = defined $selected_info->{sector_size} ? $selected_info->{sector_size} . " " . L("UNIT_BYTES") : L("VALUE_UNKNOWN");

        print &ui_hr();
        print &ui_subheading(L("SUB_ZVOL_PROPERTIES"));
        print &ui_table_start(L("TABLE_ZVOL_PROPERTIES"), "width=100%", 2);
        print &ui_table_row(L("ROW_VOLUME_DEVICE"), "/dev/zvol/" . &html_escape($selected));
        my $iscsi_target = $iscsi_target_for->($selected);
        my $backend = "/dev/zvol/$selected";
        my $iscsi_href;
        if ($iscsi_target && $iscsi_target_exists->($iscsi_target)) {
            $iscsi_href = "services.cgi?action=iscsi&edit_target=" . &url_encode($iscsi_target);
            $iscsi_href .= "&backend=" . &url_encode($backend);
        } else {
            $iscsi_href = "services.cgi?action=iscsi&backend=" . &url_encode($backend);
            $iscsi_href .= "&target=" . &url_encode($iscsi_target) if $iscsi_target;
        }
        my $iscsi_link = "<a class='button' href='" . $iscsi_href . "'>" . L("BTN_ISCSI_LINK") . "</a>";
        print &ui_table_row(L("ROW_VOLUME_ISCSI"), $iscsi_link);
        print &ui_table_row(L("ROW_VOLUME_VOLSIZE"), &html_escape($selected_info->{volsize} || '-'));
        print &ui_table_row(L("ROW_VOLUME_VOLBLOCKSIZE"), &html_escape($selected_info->{volblocksize} || '-'));
        print &ui_table_row(L("ROW_VOLUME_SECTOR_SIZE"), $sector_disp);
        print &ui_table_row(L("ROW_VOLUME_PROVISIONING"), $prov_text);
        print &ui_table_row(L("ROW_COPIES"), &html_escape($selected_info->{copies} || '-'));
        print &ui_table_row(L("ROW_VOLUME_SWAP_STATUS"), $swap_text);
        if ($sync_supported) {
            print &ui_table_row(L("ROW_VOLUME_SYNC_STATUS"), &html_escape($sync_text));
        }
        print &ui_table_end();

        if (!$selected_info->{swap_on}) {
            print &ui_alert(L("MSG_SWAP_ENABLE_WARNING"), "warning");
        } elsif ($selected_info->{swap_on} && !$selected_info->{swap_active}) {
            print &ui_alert(L("MSG_SWAP_INACTIVE_WARNING"), "warning");
        }
        if ($sync_supported && (!defined $selected_info->{sync} || $selected_info->{sync} ne 'disabled')) {
            print &ui_alert(L("MSG_SYNC_DISABLE_WARNING"), "warning");
        }
        print &ui_alert(L("MSG_PROVISIONING_INFO"), "info");

        print &ui_hr();
        print &ui_subheading(L("SUB_ZVOL_TUNING"));
        print &ui_form_start("files.cgi", "post");
        print &ui_hidden("action", "volumes");
        print &ui_hidden("manage_volume", $selected);
        print &ui_table_start(L("TABLE_ZVOL_TUNING"), "width=100%", 2);
        my $block_disp = &html_escape($selected_info->{volblocksize} || '-') . " " . L("MSG_VOLBLOCKSIZE_IMMUTABLE");
        print &ui_table_row(L("ROW_VOLUME_VOLBLOCKSIZE"), $block_disp);
        print &ui_table_row(L("ROW_COPIES"), &ui_select("volume_copies_update",
            ($selected_info->{copies} || '1'),
            [
                [ "1", "1" ],
                [ "2", "2" ],
                [ "3", "3" ],
            ]
        ));
        if ($sync_supported) {
            print &ui_table_row(L("ROW_VOLUME_SYNC"), &ui_select("volume_sync_update",
                ($selected_info->{sync} || 'standard'),
                [
                    [ "standard", L("OPT_SYNC_STANDARD") ],
                    [ "always", L("OPT_SYNC_ALWAYS") ],
                    [ "disabled", L("OPT_SYNC_DISABLED") ],
                ]
            ));
        } else {
            print &ui_table_row(L("ROW_VOLUME_SYNC"), L("MSG_SYNC_NOT_SUPPORTED_INFO"));
        }
        print &ui_table_end();
        print &ui_form_end([ [ "update_zvol_tuning", L("BTN_SAVE_CHANGES") ] ]);

        print &ui_hr();
        print &ui_subheading(L("SUB_ZVOL_SNAPSHOTS"));
        my $snapshots = zfs_list_snapshots($selected);
        my @snap_heads = (L("COL_SNAPSHOT"), L("COL_USED"), L("COL_CREATION_DATE"));
        my @snap_rows;
        for my $snap (@$snapshots) {
            my $disp = $snap->{name} || '';
            $disp =~ s/^\Q$selected\E\@//;
            push @snap_rows, [
                &html_escape($disp || $snap->{name} || '-'),
                &html_escape($snap->{used} || '-'),
                &html_escape($snap->{creation} || '-'),
            ];
        }
        print &ui_columns_table(\@snap_heads, 100, \@snap_rows, undef, 1,
            L("TABLE_ZVOL_SNAPSHOTS"), L("ERR_NO_SNAPSHOTS_FOUND"));

        print &ui_subheading(L("SUB_ZVOL_SNAPSHOT_CREATE"));
        print &ui_form_start("files.cgi", "post");
        print &ui_hidden("action", "volumes");
        print &ui_hidden("manage_volume", $selected);
        print &ui_hidden("create_zvol_snapshot", 1);
        print &ui_table_start(L("TABLE_ZVOL_SNAPSHOT_CREATE"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_SNAPSHOT_NAME"),
            &ui_textbox("zvol_snapshot_name", "", 30) . " " . L("HINT_SNAPSHOT_NAME")
        );
        print &ui_table_end();
        print &ui_form_end([ [ "create_zvol_snapshot", L("BTN_CREATE_SNAPSHOT") ] ]);

        print &ui_subheading(L("SUB_ZVOL_SNAPSHOT_DELETE"));
        print &ui_form_start("files.cgi", "post");
        print &ui_hidden("action", "volumes");
        print &ui_hidden("manage_volume", $selected);
        print &ui_hidden("destroy_zvol_snapshot", 1);
        my @snap_opts;
        for my $snap (@$snapshots) {
            my $disp = $snap->{name} || '';
            $disp =~ s/^\Q$selected\E\@//;
            push @snap_opts, [ $snap->{name}, $disp || $snap->{name} ];
        }
        push @snap_opts, [ '', L("VALUE_NONE") ] unless @snap_opts;
        print &ui_table_start(L("TABLE_ZVOL_SNAPSHOT_DELETE"), "width=100%", 2);
        print &ui_table_row(L("ROW_SNAPSHOT_SELECT"), &ui_select("zvol_snapshot_delete", "", \@snap_opts));
        print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_DESTROY"),
            &ui_checkbox("confirm_snapshot_destroy", 1, L("LBL_CONFIRM_SNAPSHOT_DESTROY"), 0));
        print &ui_table_end();
        print &ui_form_end([ [ "destroy_zvol_snapshot", L("BTN_DELETE_SNAPSHOT") ] ]);

        if (@snap_opts && $snap_opts[0][0]) {
            print &ui_hr();
            print &ui_subheading(L("SUB_ZVOL_SNAPSHOT_ROLLBACK"));
            print &ui_alert(L("MSG_SNAPSHOT_ROLLBACK_WARNING"), "warning");
            print &ui_form_start("files.cgi", "post");
            print &ui_hidden("action", "volumes");
            print &ui_hidden("manage_volume", $selected);
            print &ui_hidden("rollback_zvol_snapshot", 1);
            print &ui_table_start(L("TABLE_ZVOL_SNAPSHOT_ROLLBACK"), "width=100%", 2);
            print &ui_table_row(L("ROW_SNAPSHOT_SELECT"), &ui_select("zvol_snapshot_rollback", "", \@snap_opts));
            print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_ROLLBACK"),
                &ui_checkbox("confirm_snapshot_rollback", 1, L("LBL_CONFIRM_SNAPSHOT_ROLLBACK"), 0));
            if ($advanced_enabled) {
                my $opts = join("<br>",
                    &ui_checkbox("rollback_destroy_newer", 1, L("LBL_ROLLBACK_DESTROY_NEWER"), 0),
                    &ui_checkbox("rollback_destroy_clones", 1, L("LBL_ROLLBACK_DESTROY_CLONES"), 0),
                    &ui_checkbox("rollback_force", 1, L("LBL_ROLLBACK_FORCE"), 0),
                );
                print &ui_table_row(L("ROW_ROLLBACK_OPTIONS"), $opts);
                print &ui_table_row(L("ROW_CONFIRM_SNAPSHOT_ROLLBACK_CLONES"),
                    &ui_checkbox("confirm_snapshot_rollback_clones", 1, L("LBL_CONFIRM_SNAPSHOT_ROLLBACK_CLONES"), 0));
            }
            print &ui_table_end();
            print &ui_form_end([ [ "rollback_zvol_snapshot", L("BTN_ROLLBACK") ] ]);

            print &ui_hr();
            print &ui_subheading(L("SUB_ZVOL_SNAPSHOT_CLONE"));
            print &ui_form_start("files.cgi", "post");
            print &ui_hidden("action", "volumes");
            print &ui_hidden("manage_volume", $selected);
            print &ui_hidden("clone_zvol_snapshot", 1);
            print &ui_table_start(L("TABLE_ZVOL_SNAPSHOT_CLONE"), "width=100%", 2);
            print &ui_table_row(L("ROW_SNAPSHOT_SELECT"), &ui_select("zvol_snapshot_clone", "", \@snap_opts));
            print &ui_table_row(L("ROW_CLONE_TARGET_DATASET"),
                &ui_textbox("clone_target_dataset", "", 40) . "<br><small>" . L("HINT_CLONE_TARGET_DATASET") . "</small>");
            print &ui_table_row(L("ROW_CLONE_PROMOTE"),
                &ui_checkbox("clone_promote", 1, L("LBL_CLONE_PROMOTE"), 0));
            print &ui_table_end();
            print &ui_form_end([ [ "clone_zvol_snapshot", L("BTN_CLONE") ] ]);
        }
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_VOLUME_ACTIONS"));

    my @buttons = (
        [ "resize_volume", L("BTN_RESIZE_VOLUME") ],
        [ "destroy_volume", L("BTN_DESTROY_VOLUME") ],
    );
    if ($selected && $volinfo{$selected}) {
        if ($volinfo{$selected}{swap_on}) {
            push @buttons, [ "disable_swap", L("BTN_DISABLE_SWAP") ];
            if (!$volinfo{$selected}{swap_active}) {
                push @buttons, [ "activate_swap", L("BTN_ACTIVATE_SWAP") ];
            }
        } else {
            push @buttons, [ "enable_swap", L("BTN_ENABLE_SWAP") ];
        }
        if ($sync_supported) {
            if (defined $volinfo{$selected}{sync} && $volinfo{$selected}{sync} eq 'disabled') {
                push @buttons, [ "sync_enable", L("BTN_SYNC_ENABLE") ];
            } else {
                push @buttons, [ "sync_disable", L("BTN_SYNC_DISABLE") ];
            }
        }
        if ($volinfo{$selected}{provisioning} && $volinfo{$selected}{provisioning} eq 'full') {
            push @buttons, [ "provision_thin", L("BTN_PROVISION_THIN") ];
        } else {
            push @buttons, [ "provision_full", L("BTN_PROVISION_FULL") ];
        }
    }
    print &ui_form_end(\@buttons);

    my @vol_heads = (
        L("COL_NAME"), L("COL_USED"), L("COL_REFERENCED"),
        L("COL_VOLSIZE"), L("COL_VOLBLOCKSIZE"), L("COL_SECTOR_SIZE"),
        L("COL_PROVISIONING"), L("COL_SWAP_STATUS"), L("COL_ACTIONS"),
    );
    my @vol_rows;
    for my $v (@$vols) {
        my $info = $volinfo{$v->{name}} || {};
        my $prov = ($info->{provisioning} || 'thin') eq 'full' ? L("VALUE_FULL") : L("VALUE_THIN");
        my $swap = $info->{swap_on} ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
        my $sector = defined $info->{sector_size} ? $info->{sector_size} . " " . L("UNIT_BYTES") : "-";
        my $name_link = "<a href='files.cgi?action=volumes&manage_volume=" .
                        &url_encode($v->{name}) . "'>" .
                        &html_escape($v->{name}) . "</a>";
        my $row_target = $iscsi_target_for->($v->{name});
        my $row_backend = "/dev/zvol/$v->{name}";
        my $iscsi_row_href;
        if ($row_target && $iscsi_target_exists->($row_target)) {
            $iscsi_row_href = "services.cgi?action=iscsi&edit_target=" . &url_encode($row_target);
            $iscsi_row_href .= "&backend=" . &url_encode($row_backend);
        } else {
            $iscsi_row_href = "services.cgi?action=iscsi&backend=" . &url_encode($row_backend);
            $iscsi_row_href .= "&target=" . &url_encode($row_target) if $row_target;
        }
        my $iscsi_action = "<a class='button' href='" . $iscsi_row_href . "'>" . L("BTN_ISCSI_LINK") . "</a>";
        push @vol_rows, [
            $name_link,
            &html_escape($v->{used} || '-'),
            &html_escape($v->{refer} || '-'),
            &html_escape($v->{volsize} || '-'),
            &html_escape($v->{volblocksize} || '-'),
            $sector,
            $prov,
            $swap,
            $iscsi_action,
        ];
    }
    print &ui_columns_table(\@vol_heads, 100, \@vol_rows, undef, 1,
        L("TABLE_VOLUMES"), L("ERR_NO_VOLUMES_FOUND"));
}

sub action_permissions {
    print &ui_subheading(L("SUB_PERMISSIONS"));
    print "<p>" . L("MSG_PERMISSIONS_HELP") . "</p>";

    my $show_system = $in{'show_system'} ? 1 : 0;
    my $hide_system = $show_system ? 0 : 1;

    my $chown = $config{'chown_cmd'} || '/usr/sbin/chown';
    my $chmod = $config{'chmod_cmd'} || '/bin/chmod';
    my $find  = $config{'find_cmd'}  || '/usr/bin/find';

    my $datasets = zfs_list([qw(name mountpoint)], '-t', 'filesystem');

    my %mp_by_ds;
    for my $ds (@$datasets) {
        my $mp = $ds->{mountpoint} || '';
        next unless $mp =~ m{^/} && -d $mp;
        $mp_by_ds{$ds->{name}} = $mp;
    }

    my $list_users = sub {
        my ($hide) = @_;
        my %u;
        setpwent();
        while (my @pw = getpwent()) {
            my ($name, undef, $uid, undef) = @pw;
            next unless defined $name && length $name;
            next if $hide && defined $uid && $uid =~ /^\d+$/ && $uid < 1000 && $name ne 'root';
            $u{$name} = 1;
        }
        endpwent();
        my @names = sort keys %u;
        my @opts = map { [ $_, $_ ] } @names;
        unshift @opts, [ '', L("VALUE_NONE") ];
        return \@opts;
    };

    my $list_groups = sub {
        my ($hide) = @_;
        my %g;
        setgrent();
        while (my @gr = getgrent()) {
            my ($name, undef, $gid, undef) = @gr;
            next unless defined $name && length $name;
            next if $hide && defined $gid && $gid =~ /^\d+$/ && $gid < 1000 && $name ne 'wheel';
            $g{$name} = 1;
        }
        endgrent();
        my @names = sort keys %g;
        my @opts = map { [ $_, $_ ] } @names;
        unshift @opts, [ '', L("VALUE_NONE") ];
        return \@opts;
    };

    my $user_opts  = $list_users->($hide_system);
    my $group_opts = $list_groups->($hide_system);

    my @scope_opts = (
        [ 'filesystem', L("OPT_SCOPE_FILESYSTEM") ],
        [ 'directory',  L("OPT_SCOPE_DIRECTORY") ],
        [ 'everything', L("OPT_SCOPE_EVERYTHING") ],
    );

    if ($in{'perm_chown_apply'}) {
        my $ds = $in{'perm_chown_dataset'} || '';
        my $user = $in{'perm_chown_user'} || '';
        my $group = $in{'perm_chown_group'} || '';
        my $scope = $in{'perm_chown_scope'} || 'filesystem';

        $user =~ s/^\s+|\s+$//g;
        $group =~ s/^\s+|\s+$//g;

        my $mp = $mp_by_ds{$ds} || '';
        if (!$ds || !$mp) {
            print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
        } elsif ($scope !~ /^(filesystem|directory|everything)$/) {
            print &ui_print_error(L("ERR_PERM_SCOPE_INVALID", $scope));
        } elsif ($scope ne 'filesystem' && !$in{'perm_chown_confirm'}) {
            print &ui_print_error(L("ERR_PERM_CONFIRM_REQUIRED"));
        } elsif ($user ne '' && $user !~ /^[A-Za-z0-9_.\-]+$/) {
            print &ui_print_error(L("ERR_PERM_USER_INVALID", $user));
        } elsif ($group ne '' && $group !~ /^[A-Za-z0-9_.\-]+$/) {
            print &ui_print_error(L("ERR_PERM_GROUP_INVALID", $group));
        } elsif ($user eq '' && $group eq '') {
            print &ui_print_error(L("ERR_PERM_USER_GROUP_REQUIRED"));
        } elsif (!command_exists($chown)) {
            print &ui_print_error(L("ERR_CMD_MISSING", $chown));
        } elsif (!command_exists($find)) {
            print &ui_print_error(L("ERR_CMD_MISSING", $find));
        } else {
            my $spec = '';
            if ($user ne '' && $group ne '') {
                $spec = "$user:$group";
            } elsif ($user ne '') {
                $spec = $user;
            } else {
                $spec = ":$group";
            }
            eval {
                if ($scope eq 'filesystem') {
                    must_run($chown, '-h', $spec, $mp);
                } elsif ($scope eq 'directory') {
                    must_run($chown, '-h', $spec, $mp);
                    must_run($find, $mp, '-maxdepth', '1', '-mindepth', '1', '-exec', $chown, '-h', $spec, '{}', '+');
                } else {
                    must_run($find, $mp, '-xdev', '-exec', $chown, '-h', $spec, '{}', '+');
                }
                log_info("chown scope=$scope spec=$spec dataset=$ds mp=$mp");
                print &ui_print_success(L("SUCCESS_CHOWN_DONE", $ds));
            };
            if ($@) {
                print &ui_print_error(L("ERR_CHOWN_FAILED", $@));
            }
        }
    }

    if ($in{'perm_chmod_apply'}) {
        my $ds = $in{'perm_chmod_dataset'} || '';
        my $scope = $in{'perm_chmod_scope'} || 'filesystem';
        my $dir_mode = $in{'perm_chmod_dir'} || '';
        my $file_mode = $in{'perm_chmod_file'} || '';
        $dir_mode =~ s/^\s+|\s+$//g;
        $file_mode =~ s/^\s+|\s+$//g;

        my $mp = $mp_by_ds{$ds} || '';
        if (!$ds || !$mp) {
            print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
        } elsif ($scope !~ /^(filesystem|directory|everything)$/) {
            print &ui_print_error(L("ERR_PERM_SCOPE_INVALID", $scope));
        } elsif ($scope ne 'filesystem' && !$in{'perm_chmod_confirm'}) {
            print &ui_print_error(L("ERR_PERM_CONFIRM_REQUIRED"));
        } elsif ($dir_mode !~ /^\d{3,4}$/) {
            print &ui_print_error(L("ERR_PERM_MODE_INVALID", $dir_mode));
        } elsif ($file_mode !~ /^\d{3,4}$/) {
            print &ui_print_error(L("ERR_PERM_MODE_INVALID", $file_mode));
        } elsif (!command_exists($chmod)) {
            print &ui_print_error(L("ERR_CMD_MISSING", $chmod));
        } elsif (!command_exists($find)) {
            print &ui_print_error(L("ERR_CMD_MISSING", $find));
        } else {
            eval {
                if ($scope eq 'filesystem') {
                    must_run($chmod, '-h', $dir_mode, $mp);
                } elsif ($scope eq 'directory') {
                    must_run($find, $mp, '-maxdepth', '1', '-type', 'd', '-exec', $chmod, '-h', $dir_mode, '{}', '+');
                    must_run($find, $mp, '-maxdepth', '1', '-type', 'f', '-exec', $chmod, '-h', $file_mode, '{}', '+');
                } else {
                    must_run($find, $mp, '-xdev', '-type', 'd', '-exec', $chmod, '-h', $dir_mode, '{}', '+');
                    must_run($find, $mp, '-xdev', '-type', 'f', '-exec', $chmod, '-h', $file_mode, '{}', '+');
                }
                log_info("chmod scope=$scope dir=$dir_mode file=$file_mode dataset=$ds mp=$mp");
                print &ui_print_success(L("SUCCESS_CHMOD_DONE", $ds));
            };
            if ($@) {
                print &ui_print_error(L("ERR_CHMOD_FAILED", $@));
            }
        }
    }

    print &ui_form_start("files.cgi", "get");
    print &ui_hidden("action", "permissions");
    print &ui_table_start(L("TABLE_PERMISSIONS_FILTER"), "width=100%", 2);
    print &ui_table_row(L("ROW_SHOW_SYSTEM_ACCOUNTS"),
        &ui_checkbox("show_system", 1, L("LBL_SHOW_SYSTEM_ACCOUNTS"), $show_system));
    print &ui_table_end();
    print &ui_form_end([ [ "apply", L("BTN_VIEW") ] ]);

    my @perm_heads = (
        L("COL_FILESYSTEM"),
        L("COL_MOUNT_POINT"),
        L("COL_OWNER"),
        L("COL_GROUP"),
        L("COL_PERMISSIONS"),
    );
    my @perm_rows;
    for my $ds (@$datasets) {
        my $mp = $ds->{mountpoint} || '';
        next unless $mp =~ m{^/} && -d $mp;
        my @st = stat($mp);
        next unless @st;
        my $owner = getpwuid($st[4]) || $st[4];
        my $group = getgrgid($st[5]) || $st[5];
        my $perm = sprintf("%04o", $st[2] & 07777);
        push @perm_rows, [
            &html_escape($ds->{name}),
            &html_escape($mp),
            &html_escape($owner),
            &html_escape($group),
            &html_escape($perm),
        ];
    }
    print &ui_columns_table(\@perm_heads, 100, \@perm_rows, undef, 1,
        L("TABLE_PERMISSIONS"), L("ERR_NO_MOUNTPOINTS_FOUND"));

    my @fs_opts;
    for my $ds (sort keys %mp_by_ds) {
        push @fs_opts, [ $ds, "$ds ($mp_by_ds{$ds})" ];
    }
    unshift @fs_opts, [ '', L("VALUE_NONE") ];

    print &ui_hr();
    print &ui_subheading(L("SUB_PERM_OWNERSHIP"));
    print &ui_alert(L("MSG_PERM_RECURSIVE_WARNING"), "warning");
    print &ui_form_start("files.cgi", "post");
    print &ui_hidden("action", "permissions");
    print &ui_hidden("perm_chown_apply", 1);
    print &ui_hidden("show_system", 1) if $show_system;
    print &ui_table_start(L("TABLE_PERM_OWNERSHIP"), "width=100%", 2);
    print &ui_table_row(L("ROW_FILESYSTEM"), &ui_select("perm_chown_dataset", "", \@fs_opts));
    print &ui_table_row(L("ROW_PERM_USER"), &ui_select("perm_chown_user", "", $user_opts));
    print &ui_table_row(L("ROW_PERM_GROUP"), &ui_select("perm_chown_group", "", $group_opts));
    print &ui_table_row(L("ROW_PERM_SCOPE"), &ui_select("perm_chown_scope", "filesystem", \@scope_opts));
    print &ui_table_row(L("ROW_CONFIRM"), &ui_checkbox("perm_chown_confirm", 1, L("LBL_CONFIRM_PERM_RECURSIVE"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "perm_chown_apply", L("BTN_APPLY_OWNERSHIP") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_PERM_CHMOD"));
    print &ui_alert(L("MSG_PERM_RECURSIVE_WARNING"), "warning");
    print &ui_form_start("files.cgi", "post");
    print &ui_hidden("action", "permissions");
    print &ui_hidden("perm_chmod_apply", 1);
    print &ui_hidden("show_system", 1) if $show_system;
    print &ui_table_start(L("TABLE_PERM_CHMOD"), "width=100%", 2);
    print &ui_table_row(L("ROW_FILESYSTEM"), &ui_select("perm_chmod_dataset", "", \@fs_opts));
    print &ui_table_row(L("ROW_PERM_DIR_MODE"), &ui_textbox("perm_chmod_dir", "0755", 6));
    print &ui_table_row(L("ROW_PERM_FILE_MODE"), &ui_textbox("perm_chmod_file", "0644", 6));
    print &ui_table_row(L("ROW_PERM_SCOPE"), &ui_select("perm_chmod_scope", "filesystem", \@scope_opts));
    print &ui_table_row(L("ROW_CONFIRM"), &ui_checkbox("perm_chmod_confirm", 1, L("LBL_CONFIRM_PERM_RECURSIVE"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "perm_chmod_apply", L("BTN_APPLY_PERMISSIONS") ] ]);
}

1;
