#!/usr/bin/env perl

package main;

use strict;
use warnings;
use Cwd qw(realpath);
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

our %config;

# Parse CGI params
zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => "TITLE_DISKS");

eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('disks'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'disks'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'list';
$action = '' unless defined $action;
$action =~ s/\0.*$//s;
$action =~ s/[&;].*$//;
$action =~ s/^\s+|\s+$//g;
$action = 'list' if $action eq '';
my $disk   = $in{'disk'} || '';
my $advanced_enabled = cfg_bool('advanced_mode', 0);

# Plain anchor tabs for reliable switching (works with &ReadParse)
my @tabs_list = (
    [ 'list', 'TAB_DISKS' ],
    [ 'smart', 'TAB_SMART' ],
    [ 'monitor', 'TAB_IO_MONITOR' ],
    [ 'memory', 'TAB_MEMORY' ],
    [ 'benchmark', 'TAB_BENCHMARK' ],
    [ 'advanced', 'TAB_ADVANCED' ],
);
@tabs_list = grep { $_->[0] ne 'memory' && $_->[0] ne 'benchmark' } @tabs_list unless $advanced_enabled;

print zfsguru_print_tabs(
    script => 'disks.cgi',
    active => $action,
    tabs   => \@tabs_list,
);

if ($action eq 'list' || !$action) {
    &action_list();
} elsif ($action eq 'detail') {
    &action_detail();
} elsif ($action eq 'smart') {
    &action_smart();
} elsif ($action eq 'monitor') {
    &action_monitor();
} elsif ($action eq 'memory') {
    if (!$advanced_enabled) {
        &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        &action_list();
    } else {
        &action_memory();
    }
} elsif ($action eq 'benchmark') {
    &action_benchmark();
} elsif ($action eq 'query') {
    &action_query();
} elsif ($action eq 'wipe_log') {
    &action_wipe_log();
} elsif ($action eq 'job_log') {
    &action_job_log();
} elsif ($action eq 'format') {
    &action_format();
} elsif ($action eq 'advanced') {
    &action_advanced();
} else {
    &action_list();
}

my $back_url = 'index.cgi';
if ($action ne 'list') {
    if ($action eq 'benchmark' || ($action eq 'job_log' && ($in{'job'} || '') =~ /^diskbench_[A-Za-z0-9_.\-]+\.log$/)) {
        $back_url = 'disks.cgi?action=benchmark';
    } else {
        $back_url = 'disks.cgi?action=list';
    }
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_list {
    my $disks = disk_list();
    my %diskset = map { $_ => 1 } @$disks;

    if ($in{'mass_process'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } else {
            my @selected = grep { $in{"selectdisk_$_"} } @$disks;
            if (!@selected) {
                print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            } elsif (!$in{'confirm_mass'}) {
                print &ui_print_error(L("ERR_CONFIRM_MASS_REQUIRED"));
            } else {
                my $action = $in{'mass_action'} || '';
                my (@ok_html, @err_html);
                my $background = $in{'mass_background'} ? 1 : 0;
                my $label_prefix = $in{'mass_label_prefix'} || '';
                my $label_start = $in{'mass_label_start'} || 1;
                $label_start = 1 unless $label_start =~ /^\d+$/;

                if ($action eq 'format_gpt') {
                    if (!length $label_prefix || !is_label_name($label_prefix)) {
                        print &ui_print_error(L("ERR_MASS_LABEL_PREFIX"));
                        $action = '';
                    }
                }
                if ($action) {
                    my $view_link_for = sub {
                        my ($log_name, $disk_name) = @_;
                        my $url = "disks.cgi?action=job_log&job=" . &url_encode($log_name) .
                                  "&disk=" . &url_encode($disk_name);
                        return "<a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" .
                               &html_escape($url) . "'>" . &html_escape(L("BTN_VIEW_LOG")) . "</a>";
                    };
                    my $label_counter = $label_start;
                    for my $disk (@selected) {
                        next unless $diskset{$disk};
                        my $dev = "/dev/$disk";
                        eval {
                            if ($action eq 'format_gpt') {
                                run_cmd($zfsguru_lib::GPART, 'destroy', '-F', $disk);
                                must_run($zfsguru_lib::GPART, 'create', '-s', 'gpt', $disk);
                                my $label = $label_prefix . $label_counter++;
                                my @args = ($zfsguru_lib::GPART, 'add', '-t', 'freebsd-zfs', '-a', '1M', '-l', $label, $disk);
                                must_run(@args);
                                push @ok_html, &html_escape(L("SUCCESS_MASS_FORMAT_GPT", $disk, $label));
                            } elsif ($action eq 'format_mbr') {
                                run_cmd($zfsguru_lib::GPART, 'destroy', '-F', $disk);
                                must_run($zfsguru_lib::GPART, 'create', '-s', 'mbr', $disk);
                                must_run($zfsguru_lib::GPART, 'add', '-t', 'freebsd', $disk);
                                push @ok_html, &html_escape(L("SUCCESS_MASS_FORMAT_MBR", $disk));
                            } elsif ($action eq 'wipe_zero') {
                                if ($background) {
                                    my ($ok, $job_id, $log, $err) = start_wipe_job(mode => 'zero', device => $dev);
                                    die $err unless $ok;
                                    my $view = $view_link_for->($log, $disk);
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $log)) . " " . $view;
                                } else {
                                    my ($ok, $err) = disk_zero_write($dev);
                                    die $err unless $ok;
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_ZERO", $dev));
                                }
                            } elsif ($action eq 'wipe_random') {
                                if ($background) {
                                    my ($ok, $job_id, $log, $err) = start_wipe_job(mode => 'random', device => $dev);
                                    die $err unless $ok;
                                    my $view = $view_link_for->($log, $disk);
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $log)) . " " . $view;
                                } else {
                                    my ($ok, $err) = disk_random_write($dev);
                                    die $err unless $ok;
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_RANDOM", $dev));
                                }
                            } elsif ($action eq 'wipe_secure') {
                                if ($background) {
                                    my ($ok, $job_id, $log, $err) = start_wipe_job(mode => 'secure', device => $dev);
                                    die $err unless $ok;
                                    my $view = $view_link_for->($log, $disk);
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $log)) . " " . $view;
                                } else {
                                    my ($ok, $err) = disk_secure_erase($dev);
                                    die $err unless $ok;
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_SECURE", $dev));
                                }
                            } elsif ($action eq 'wipe_ata') {
                                my ($ata_ok, $ata_why) = ata_secure_erase_available();
                                if (!$ata_ok) {
                                    die L("MSG_WIPE_ATA_UNAVAILABLE") . ($ata_why ? " ($ata_why)" : "");
                                }
                                if ($background) {
                                    my ($ok, $job_id, $log, $err) = start_wipe_job(mode => 'ata', device => $dev);
                                    die $err unless $ok;
                                    my $view = $view_link_for->($log, $disk);
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $log)) . " " . $view;
                                } else {
                                    my ($ok, $err) = disk_ata_secure_erase($dev);
                                    die $err unless $ok;
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_ATA", $dev));
                                }
                            } elsif ($action eq 'wipe_discard') {
                                if (!command_exists($zfsguru_lib::BLKDISCARD)) {
                                    die L("MSG_WIPE_DISCARD_UNAVAILABLE");
                                }
                                if ($background) {
                                    my ($ok, $job_id, $log, $err) = start_wipe_job(mode => 'discard', device => $dev);
                                    die $err unless $ok;
                                    my $view = $view_link_for->($log, $disk);
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $log)) . " " . $view;
                                } else {
                                    my ($ok, $err) = disk_blkdiscard($dev);
                                    die $err unless $ok;
                                    push @ok_html, &html_escape(L("SUCCESS_WIPE_DISCARD", $dev));
                                }
                            } else {
                                die L("ERR_MASS_ACTION_INVALID");
                            }
                        };
                        if ($@) {
                            push @err_html, &html_escape(L("ERR_MASS_ACTION_FAILED", $disk, $@));
                        }
                    }
                }
                print &ui_print_success(join("<br />", @ok_html)) if @ok_html;
                print &ui_print_error(join("<br />", @err_html)) if @err_html;
            }
        }
    }
    
    my $dmesg_map = disk_dmesg_map($disks);
    my $geom_labels = disk_geom_labels_map();
    my $gpt_labels = disk_gpt_labels_map($disks);
    my %label_seen;
    my @label_conflicts;
    my @no_devnode;
    my @no_labeldev;

    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "list");

    my @inv_heads = (
        L("COL_DISK"),
        L("COL_LABEL"),
        L("COL_SIZE"),
        L("COL_SECTOR_COUNT"),
        L("COL_SECTOR_SIZE"),
        L("COL_IDENTIFIED_AS"),
        L("COL_SELECT"),
        L("COL_ACTIONS"),
    );
    my @inv_data;
    
    for my $disk (@$disks) {
        my $info = diskinfo($disk);
        my $size = $info ? &format_bytes($info->{mediasize}) : L("VALUE_UNKNOWN");
        my $sectors = $info ? $info->{sectorcount} : L("VALUE_UNKNOWN");
        my $sect_sz = $info ? $info->{sectorsize} : L("VALUE_UNKNOWN");
        my $ident = $dmesg_map->{$disk} || '-';
        my @labels;
        if ($geom_labels->{$disk}) {
            for my $l (@{ $geom_labels->{$disk} }) {
                push @labels, "GEOM: " . &html_escape($l);
                my $k = "geom:$l";
                push @label_conflicts, $l if $label_seen{$k}++;
            }
        }
        if ($gpt_labels->{$disk}) {
            for my $l (@{ $gpt_labels->{$disk} }) {
                push @labels, "GPT: " . &html_escape($l);
                my $k = "gpt:$l";
                push @label_conflicts, $l if $label_seen{$k}++;
                if (!-e "/dev/gpt/$l") {
                    push @no_labeldev, $l;
                }
            }
        }
        my $label_str = @labels ? join("<br />", @labels) : "-";
        push @no_devnode, $disk unless -e "/dev/$disk";
        
        my @btns = (
            &ui_link_icon("disks.cgi?action=detail&disk=" . &url_encode($disk), L("BTN_DETAILS"), undef, { class => 'default' }),
            &ui_link_icon("disks.cgi?action=smart&disk=" . &url_encode($disk), L("TAB_SMART"), undef, { class => 'default' }),
            &ui_link_icon("disks.cgi?action=query&disk=" . &url_encode($disk), L("BTN_QUERY"), undef, { class => 'default' }),
            &ui_link_icon("disks.cgi?action=format&disk=" . &url_encode($disk), L("BTN_FORMAT"), undef, { class => 'danger' }),
        );
        my $actions = "<div class='zfsguru-actionlinks'>" . join(" ", @btns) . "</div>";

        push @inv_data, [
            &html_escape($disk),
            $label_str,
            &html_escape($size),
            &html_escape($sectors),
            &html_escape($sect_sz),
            &html_escape($ident),
            &ui_checkbox("selectdisk_$disk", 1, "", 0),
            $actions,
        ];
    }
    print &ui_columns_table(\@inv_heads, 100, \@inv_data, undef, 1,
        L("TABLE_DISK_INVENTORY"), L("ERR_NO_DISKS_FOUND"));

    if (@label_conflicts) {
        my %uniq;
        my @conf = grep { !$uniq{$_}++ } @label_conflicts;
        print &ui_alert(L("WARN_LABEL_CONFLICT", join(', ', @conf)), "warning");
    }
    if (@no_devnode) {
        my %uniq;
        my @list = grep { !$uniq{$_}++ } @no_devnode;
        print &ui_alert(L("WARN_NODEVNODE", join(', ', @list)), "warning");
    }
    if (@no_labeldev) {
        my %uniq;
        my @list = grep { !$uniq{$_}++ } @no_labeldev;
        print &ui_alert(L("WARN_LABEL_NOT_USED", join(', ', @list)), "warning");
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_DISK_MASS_ACTIONS"));
    print &ui_table_start(L("TABLE_DISK_MASS_ACTIONS"), "width=100%", 2);
    print &ui_table_row(L("ROW_MASS_ACTION"),
        &ui_select("mass_action", "", [
            [ "", "" ],
            [ "format_gpt", L("OPT_MASS_FORMAT_GPT") ],
            [ "format_mbr", L("OPT_MASS_FORMAT_MBR") ],
            [ "wipe_zero", L("OPT_MASS_WIPE_ZERO") ],
            [ "wipe_random", L("OPT_MASS_WIPE_RANDOM") ],
            [ "wipe_secure", L("OPT_MASS_WIPE_SECURE") ],
            [ "wipe_ata", L("OPT_MASS_WIPE_ATA") ],
            [ "wipe_discard", L("OPT_MASS_WIPE_DISCARD") ],
        ])
    );
    print &ui_table_row(L("ROW_MASS_LABEL_PREFIX"),
        &ui_textbox("mass_label_prefix", "", 20) . " " . L("HINT_MASS_LABEL_PREFIX"));
    print &ui_table_row(L("ROW_MASS_LABEL_START"),
        &ui_textbox("mass_label_start", "1", 6));
    print &ui_table_row(L("ROW_MASS_BACKGROUND"),
        &ui_checkbox("mass_background", 1, L("LBL_MASS_BACKGROUND"), 0));
    print &ui_table_row(L("ROW_MASS_CONFIRM"),
        &ui_checkbox("confirm_mass", 1, L("LBL_CONFIRM_MASS"), 0));
    print &ui_table_end();

    print &ui_form_end([ [ "mass_process", L("BTN_MASS_EXECUTE") ] ]);
}

sub action_detail {
    my $disk_name = $in{'disk'};
    return unless $disk_name;
    
    my $info = diskinfo($disk_name);
    if (!$info) {
        print &ui_print_error(L("ERR_DISKINFO_FAILED", $disk_name));
        return;
    }
    
    my $dev_path = ($disk_name =~ m{^/dev/}) ? $disk_name : "/dev/$disk_name";
    my $sector_size = (defined $info->{sectorsize} && $info->{sectorsize} ne '')
        ? ($info->{sectorsize} . " " . L("UNIT_BYTES"))
        : L("VALUE_UNKNOWN");
    my $sector_count = defined $info->{sectorcount} ? $info->{sectorcount} : L("VALUE_UNKNOWN");
    my $stripe_size = (defined $info->{stripesize} && $info->{stripesize} ne '')
        ? ($info->{stripesize} . " " . L("UNIT_BYTES"))
        : L("VALUE_UNKNOWN");
    my $stripe_offset = (defined $info->{stripeoffset} && $info->{stripeoffset} ne '')
        ? ($info->{stripeoffset} . " " . L("UNIT_BYTES"))
        : L("VALUE_UNKNOWN");
    my $media_bytes = defined $info->{mediasize} ? $info->{mediasize} : L("VALUE_UNKNOWN");

    my $identify = disk_identify($disk_name) || {};
    my $identify_raw = $identify->{raw} || '';
    my $identify_snip = '';
    if ($identify_raw ne '') {
        my @lines = grep { /\S/ } split /\n/, $identify_raw;
        @lines = @lines[0 .. ($#lines > 9 ? 9 : $#lines)] if @lines;
        $identify_snip = join("\n", @lines);
    }

    my $geom_map = disk_geom_labels_map();
    my $gpt_map  = disk_gpt_labels_map([ $disk_name ]);
    my @geom_labels = ();
    my @gpt_labels = ();
    if ($geom_map && ref($geom_map) eq 'HASH' && $geom_map->{$disk_name}) {
        @geom_labels = @{ $geom_map->{$disk_name} || [] };
    }
    if ($gpt_map && ref($gpt_map) eq 'HASH' && $gpt_map->{$disk_name}) {
        @gpt_labels = @{ $gpt_map->{$disk_name} || [] };
    }

    my %pool_membership_by_role = (
        data  => {},
        cache => {},
        log   => {},
        spare => {},
    );
    my @needles = ($disk_name);
    my @parts = map { $_->{name} } @{ disk_partition_map($disk_name) || [] };
    push @needles, @parts;
    push @needles, @geom_labels, map { "label/$_" } @geom_labels;
    push @needles, @gpt_labels, map { "gpt/$_" } @gpt_labels;
    my %needle = map {
        my $n = lc($_ // '');
        $n =~ s{^/dev/}{};
        $n => 1
    } grep { defined($_) && $_ ne '' } @needles;
    my $disk_lc = lc($disk_name);

    my $zs = zpool_status() // '';
    my ($cur_pool, $in_cfg, $role) = ('', 0, 'data');
    for my $ln (split /\n/, $zs) {
        if ($ln =~ /^\s*pool:\s*(\S+)/) {
            $cur_pool = $1;
            $in_cfg = 0;
            $role = 'data';
            next;
        }
        next unless $cur_pool ne '';
        if ($ln =~ /^\s*config:/) {
            $in_cfg = 1;
            $role = 'data';
            next;
        }
        next unless $in_cfg;
        if ($ln =~ /^\s*(logs|cache|spares)\s*$/i) {
            my $grp = lc($1);
            $role = $grp eq 'logs' ? 'log'
                : $grp eq 'spares' ? 'spare'
                : 'cache';
            next;
        }
        next if $ln =~ /^\s*NAME\s+STATE/i;
        if ($ln =~ /^\s+(\S+)\s+(ONLINE|OFFLINE|DEGRADED|FAULTED|UNAVAIL|REMOVED|AVAIL|INUSE)/i) {
            my $dn = lc($1 || '');
            next if $dn eq '' || $dn eq lc($cur_pool);
            next if $dn =~ /^(?:mirror|raidz\d*)/i;
            $dn =~ s{^/dev/}{};
            my $matched = $needle{$dn} ? 1 : 0;
            if (!$matched && $dn =~ m{^(?:gpt|label)/(.+)$}) {
                $matched = $needle{$1} ? 1 : 0;
            }
            if (!$matched && $dn =~ /^\Q$disk_lc\E[ps]\d+$/) {
                $matched = 1;
            }
            if ($matched) {
                $pool_membership_by_role{$role}{$cur_pool} = 1;
            }
        }
    }

    my %pool_union = ();
    for my $r (keys %pool_membership_by_role) {
        $pool_union{$_} = 1 for keys %{ $pool_membership_by_role{$r} || {} };
    }
    my @pool_list = sort keys %pool_union;
    my @pool_data  = sort keys %{ $pool_membership_by_role{data}  || {} };
    my @pool_cache = sort keys %{ $pool_membership_by_role{cache} || {} };
    my @pool_log   = sort keys %{ $pool_membership_by_role{log}   || {} };
    my @pool_spare = sort keys %{ $pool_membership_by_role{spare} || {} };

    my @swap_hits;
    my $swap_list = swapctl_list();
    for my $sw (@{ $swap_list || [] }) {
        my $dev = lc($sw->{device} || '');
        next unless $dev ne '';
        $dev =~ s{^/dev/}{};
        my $matched = $needle{$dev} ? 1 : 0;
        if (!$matched && $dev =~ m{^(?:gpt|label)/(.+)$}) {
            $matched = $needle{$1} ? 1 : 0;
        }
        if (!$matched && $dev =~ /^\Q$disk_lc\E[ps]\d+$/) {
            $matched = 1;
        }
        push @swap_hits, $sw->{device} if $matched;
    }

    my %pool_role_labels;
    for my $pn (@pool_data)  { push @{ $pool_role_labels{$pn} }, 'data'; }
    for my $pn (@pool_cache) { push @{ $pool_role_labels{$pn} }, 'cache'; }
    for my $pn (@pool_log)   { push @{ $pool_role_labels{$pn} }, 'log'; }
    for my $pn (@pool_spare) { push @{ $pool_role_labels{$pn} }, 'spare'; }
    my @pool_summary = ();
    for my $pn (sort keys %pool_role_labels) {
        my @roles = @{ $pool_role_labels{$pn} || [] };
        push @pool_summary, $pn . '(' . join('+', @roles) . ')';
    }

    print &ui_subheading(L("SUB_DISK_DETAILS", $disk_name));
    print &ui_table_start(L("TABLE_DISK_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_DISK_NAME"), &html_escape($disk_name));
    print &ui_table_row("Device Path", &html_escape($dev_path));
    print &ui_table_row("Pool Membership", @pool_list ? &html_escape(join(", ", @pool_list)) : L("VALUE_NONE"));
    print &ui_table_row("Pool Membership Summary", @pool_summary ? &html_escape(join(", ", @pool_summary)) : L("VALUE_NONE"));
    print &ui_table_row("Pool Role: data", @pool_data ? &html_escape(join(", ", @pool_data)) : L("VALUE_NONE"));
    print &ui_table_row("Pool Role: cache", @pool_cache ? &html_escape(join(", ", @pool_cache)) : L("VALUE_NONE"));
    print &ui_table_row("Pool Role: log", @pool_log ? &html_escape(join(", ", @pool_log)) : L("VALUE_NONE"));
    print &ui_table_row("Pool Role: spare", @pool_spare ? &html_escape(join(", ", @pool_spare)) : L("VALUE_NONE"));
    print &ui_table_row("Swap Usage", @swap_hits ? &html_escape(join(", ", @swap_hits)) : L("VALUE_NONE"));
    print &ui_table_row("GPT Labels", @gpt_labels ? &html_escape(join(", ", @gpt_labels)) : L("VALUE_NONE"));
    print &ui_table_row("GEOM Labels", @geom_labels ? &html_escape(join(", ", @geom_labels)) : L("VALUE_NONE"));
    print &ui_table_row(L("ROW_MEDIA_SIZE"), &format_bytes($info->{mediasize}));
    print &ui_table_row("Media Size (bytes)", &html_escape($media_bytes));
    print &ui_table_row(L("ROW_SECTOR_SIZE"), &html_escape($sector_size));
    print &ui_table_row(L("ROW_SECTOR_COUNT"), &html_escape($sector_count));
    print &ui_table_row(L("ROW_STRIPE_SIZE"), &html_escape($stripe_size));
    print &ui_table_row(L("ROW_STRIPE_OFFSET"), &html_escape($stripe_offset));
    print &ui_table_end();

    my @part_rows;
    my @part_heads = (
        "Partition",
        "Label",
        "Type",
        "Start (sectors)",
        "Size (sectors)",
        "Approx Size",
        "Pool Role",
        "Swap",
    );
    my $sect_size_num = ($info->{sectorsize} && $info->{sectorsize} =~ /^\d+$/) ? $info->{sectorsize}+0 : 0;
    my %role_by_pool = ();
    $role_by_pool{$_} = 'data' for @pool_data;
    $role_by_pool{$_} = 'cache' for @pool_cache;
    $role_by_pool{$_} = 'log' for @pool_log;
    $role_by_pool{$_} = 'spare' for @pool_spare;
    my %swap_dev = map {
        my $d = lc($_);
        $d =~ s{^/dev/}{};
        $d => 1
    } @swap_hits;

    for my $p (@parts) {
        my $plabel = '-';
        my $ptype = '-';
        my $start = '-';
        my $psz = '-';
        my $bytes_h = '-';
        my $pool_role = '-';
        my $is_swap = 'no';
        my $plist = disk_partition_map($disk_name) || [];
        for my $pi (@$plist) {
            next unless ref($pi) eq 'HASH';
            next unless ($pi->{name} || '') eq $p;
            $plabel = $pi->{label} if defined $pi->{label} && $pi->{label} ne '';
            $ptype = $pi->{type} if defined $pi->{type} && $pi->{type} ne '';
            $start = $pi->{start} if defined $pi->{start};
            $psz = $pi->{size} if defined $pi->{size};
            if ($sect_size_num && defined $pi->{size} && $pi->{size} =~ /^\d+$/) {
                $bytes_h = format_bytes(($pi->{size}+0) * $sect_size_num);
            }
            last;
        }
        my $pool = '';
        for my $r (qw(data cache log spare)) {
            for my $pn (keys %{ $pool_membership_by_role{$r} || {} }) {
                my $zs = zpool_status($pn) // '';
                if ($zs =~ m{(?:^|\s)(?:/dev/)?\Q$p\E(?:\s|$)}m ||
                    $zs =~ m{(?:^|\s)gpt/\Q$p\E(?:\s|$)}m ||
                    $zs =~ m{(?:^|\s)label/\Q$p\E(?:\s|$)}m) {
                    $pool = $pn;
                    $pool_role = $r;
                    last;
                }
            }
            last if $pool ne '';
        }
        if ($pool eq '') {
            $pool_role = L("VALUE_NONE");
        } else {
            $pool_role = "$pool ($pool_role)";
        }
        $is_swap = 'yes' if $swap_dev{lc($p)};

        push @part_rows, [
            html_escape($p),
            html_escape($plabel),
            html_escape($ptype),
            html_escape($start),
            html_escape($psz),
            html_escape($bytes_h),
            html_escape($pool_role),
            html_escape($is_swap),
        ];
    }
    print &ui_subheading("Partitions");
    print &ui_columns_table(
        \@part_heads,
        100,
        \@part_rows,
        undef,
        1,
        undef,
        "No partitions found on this disk"
    );

    my $raw = $info->{raw} || '';
    if ($raw ne '') {
        print &ui_subheading("Raw diskinfo output");
        print "<pre>" . &html_escape($raw) . "</pre>";
    }
    if ($identify_snip ne '') {
        print &ui_subheading("CAM identify (first lines)");
        print "<pre>" . &html_escape($identify_snip) . "</pre>";
    }
}

sub action_smart {
    my $disk_name = $in{'disk'};
    my $disks = disk_list();
    my @disk_opts = map { [ $_, $_ ] } @{ $disks || [] };
    if (!$disk_name) {
        $disk_name = @$disks ? $disks->[0] : '';
    }
    if (!$disk_name) {
        print &ui_print_error(L("ERR_NO_DISKS_FOUND"));
        return;
    }
    my %diskset = map { $_ => 1 } @{ $disks || [] };
    if (!$diskset{$disk_name}) {
        print &ui_print_error(L("ERR_DISK_INVALID", $disk_name));
        return;
    }

    my $smart_link = "disks.cgi?action=smart&disk=" . &url_encode($disk_name);
    my $query_link = "disks.cgi?action=query&disk=" . &url_encode($disk_name);
    my $adv_link   = "disks.cgi?action=advanced&disk=" . &url_encode($disk_name);
    print &ui_table_start("Quick Actions", "width=100%", 2);
    print &ui_table_row("Disk",
        &ui_link_icon($smart_link, &html_escape($disk_name), undef, { class => 'default' }));
    print &ui_table_row("Actions",
        &ui_link_icon($smart_link, "Refresh SMART", undef, { class => 'primary' }) . " " .
        &ui_link_icon($query_link, "Open Partition Modify", undef, { class => 'default' }) . " " .
        &ui_link_icon($adv_link, "Open Advanced", undef, { class => 'default' }));
    print &ui_table_end();

    print &ui_form_start("disks.cgi", "get");
    print &ui_hidden("action", "smart");
    print &ui_table_start("SMART Disk Selection", "width=100%", 2);
    print &ui_table_row(L("COL_DISK"), &ui_select("disk", $disk_name, \@disk_opts));
    print &ui_table_end();
    print &ui_form_end([ [ "open_smart", "Open SMART" ] ]);
    
    if ($in{'enable_smart'}) {
        my ($ok, $out, $err) = smart_enable($disk_name);
        if ($ok) {
            print &ui_print_success(L("SUCCESS_SMART_ENABLED", $disk_name));
        } else {
            print &ui_print_error(L("ERR_SMART_ENABLE_FAILED", $err));
        }
    }
    
    print &ui_subheading(L("SUB_SMART_INFO", $disk_name));
    
    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "smart");
    print &ui_hidden("disk", $disk_name);
    print &ui_form_end([ [ "enable_smart", L("BTN_ENABLE_SMART") ] ]);
    
    my $smart_raw = smart_info($disk_name);
    if (!$smart_raw) {
        print &ui_print_error(L("ERR_SMART_INFO_FAILED", $disk_name));
        return;
    }
    my $smart_backend = smart_detected_backend($disk_name);
    print &ui_table_start("SMART Backend", "width=100%", 2);
    print &ui_table_row("Detected SMART backend", &html_escape($smart_backend || 'direct'));
    print &ui_table_end();

    my @attrs;
    for my $ln (split /\n/, $smart_raw) {
        next unless $ln =~ /^\s*(\d+)\s+([A-Za-z0-9_\-]+)\s+\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(.+)$/;
        push @attrs, {
            id => $1,
            attribute => $2,
            value => $3,
            worst => $4,
            thresh => $5,
            raw => $6,
        };
    }

    if (@attrs) {
        my @heads = (L("COL_ID"), L("COL_ATTRIBUTE"), L("COL_VALUE"), L("COL_WORST"), L("COL_THRESHOLD"));
        my @data;
        for my $attr (@attrs) {
            my $status = L("VALUE_OK");
            if (defined $attr->{value} && defined $attr->{thresh} && $attr->{value} < $attr->{thresh}) {
                $status = "<span class='zfsguru-status-bad'>" . L("VALUE_WARNING") . "</span>";
            }
            push @data, [
                &html_escape($attr->{id}),
                &html_escape($attr->{attribute}),
                &html_escape($attr->{value}) . " $status",
                &html_escape($attr->{worst}),
                &html_escape($attr->{thresh}),
            ];
        }
        print &ui_columns_table(\@heads, 100, \@data, undef, 1,
            L("TABLE_SMART_ATTRS"), L("ERR_NO_SMART_ATTRS"));
    } else {
        print &ui_alert("SMART attribute table was not parsed; showing raw smartctl output.", "info");
    }
    print &ui_subheading("Raw smartctl output");
    print "<pre>" . &html_escape($smart_raw) . "</pre>";
    if (!@attrs) {
        print &ui_print_error(L("ERR_NO_SMART_ATTRS"));
    }
}

sub cfg_bool {
    my ($key, $default) = @_;
    my $v = $config{$key};
    my $cfg_file = "$Bin/config.txt";
    if (-r $cfg_file) {
        if (open(my $fh, '<', $cfg_file)) {
            while (my $line = <$fh>) {
                chomp $line;
                $line =~ s/^\s+|\s+$//g;
                next if $line eq '' || $line =~ /^#/;
                next unless $line =~ /^([A-Za-z0-9_\-]+)\s*=\s*(.*)$/;
                my ($k, $val) = ($1, $2);
                next unless $k eq $key;
                $v = $val;
                last;
            }
            close($fh);
        }
    }
    return $default if !defined $v;
    $v =~ s/^\s+|\s+$//g;
    return 1 if $v =~ /^(?:1|yes|true|on)$/i;
    return 0 if $v =~ /^(?:0|no|false|off)$/i;
    return $default;
}

sub disk_benchmark_profiles {
    return {
        quick_read => {
            label       => L("OPT_DISK_BENCH_QUICK_READ"),
            destructive => 0,
            engine      => 'diskinfo',
        },
        seq_read => {
            label       => L("OPT_DISK_BENCH_SEQ_READ"),
            destructive => 0,
            rw          => 'read',
            bs          => '1M',
        },
        rand_read => {
            label       => L("OPT_DISK_BENCH_RAND_READ"),
            destructive => 0,
            rw          => 'randread',
            bs          => '4k',
        },
        seq_write => {
            label       => L("OPT_DISK_BENCH_SEQ_WRITE"),
            destructive => 1,
            rw          => 'write',
            bs          => '1M',
        },
        rand_write => {
            label       => L("OPT_DISK_BENCH_RAND_WRITE"),
            destructive => 1,
            rw          => 'randwrite',
            bs          => '4k',
        },
    };
}

sub disk_benchmark_job {
    my (%opt) = @_;
    my $disk = $opt{disk} || '';
    my $profile = $opt{profile} || 'quick_read';
    my $duration = $opt{duration} || 20;
    my $size_mib = $opt{size_mib} || 1024;
    my $iodepth = $opt{iodepth} || 8;

    die "Invalid disk" unless is_disk_name($disk);
    my $dev = ($disk =~ m{^/dev/}) ? $disk : "/dev/$disk";
    die "Invalid benchmark profile" unless disk_benchmark_profiles()->{$profile};

    my $prof = disk_benchmark_profiles()->{$profile};
    print "Disk benchmark\n";
    print "Device   : $dev\n";
    print "Profile  : $profile\n";
    print "Duration : ${duration}s\n";
    print "Size     : ${size_mib} MiB\n";
    print "I/O depth: $iodepth\n";
    print "\n";

    if ($prof->{engine} && $prof->{engine} eq 'diskinfo') {
        my $diskinfo = $zfsguru_lib::DISKINFO || '/usr/sbin/diskinfo';
        die "diskinfo command not found" unless command_exists($diskinfo);
        my @cmd = ($diskinfo, '-ct', $dev);
        print ">> " . join(' ', @cmd) . "\n";
        my ($rc, $out, $err) = run_cmd(@cmd);
        print $out if defined $out && length $out;
        print $err if defined $err && length $err;
        die "diskinfo benchmark failed" if $rc != 0;
        return;
    }

    my $fio = $config{'fio_cmd'} || '/usr/local/bin/fio';
    die L("ERR_DISK_BENCH_FIO_NOT_FOUND", $fio) unless command_exists($fio);

    my @cmd = (
        $fio,
        '--name=zfsguru-disk-bench',
        "--filename=$dev",
        '--ioengine=sync',
        '--direct=1',
        '--time_based=1',
        "--runtime=$duration",
        "--size=${size_mib}M",
        '--numjobs=1',
        '--group_reporting=1',
        "--rw=$prof->{rw}",
        "--bs=$prof->{bs}",
        "--iodepth=$iodepth",
    );
    push @cmd, '--readonly=1' unless $prof->{destructive};

    print ">> " . join(' ', @cmd) . "\n";
    my ($rc, $out, $err) = run_cmd(@cmd);
    print $out if defined $out && length $out;
    print $err if defined $err && length $err;
    die "fio benchmark failed" if $rc != 0;
}

sub _disk_bench_rate_to_mib {
    my ($rate_txt) = @_;
    return undef unless defined $rate_txt;
    $rate_txt =~ s/^\s+|\s+$//g;
    return undef if $rate_txt eq '';
    if ($rate_txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?i?B)\/s$/i) {
        my ($num, $unit) = ($1 + 0, uc($2));
        my %f = (
            B   => 1 / (1024 * 1024),
            KIB => 1 / 1024,
            MIB => 1,
            GIB => 1024,
            TIB => 1024 * 1024,
            KB  => 1000 / (1024 * 1024),
            MB  => (1000 * 1000) / (1024 * 1024),
            GB  => (1000 * 1000 * 1000) / (1024 * 1024),
            TB  => (1000 * 1000 * 1000 * 1000) / (1024 * 1024),
        );
        return undef unless exists $f{$unit};
        return $num * $f{$unit};
    }
    if ($rate_txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*(?:bytes\/sec|bytes\/second|bytes per second)$/i) {
        return ($1 + 0) / (1024 * 1024);
    }
    if ($rate_txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*(?:kbytes\/sec|kbytes\/second|kbytes per second)$/i) {
        return ($1 + 0) / 1024;
    }
    if ($rate_txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*(?:mbytes\/sec|mbytes\/second|mbytes per second)$/i) {
        return ($1 + 0);
    }
    if ($rate_txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*(?:gbytes\/sec|gbytes\/second|gbytes per second)$/i) {
        return ($1 + 0) * 1024;
    }
    if ($rate_txt =~ /^([0-9]+(?:\.[0-9]+)?)$/) {
        return ($1 + 0) / (1024 * 1024);
    }
    return undef;
}

sub _disk_bench_secs_human {
    my ($secs) = @_;
    return '' unless defined $secs && $secs =~ /^[0-9]+(?:\.[0-9]+)?$/;
    return sprintf("%.3f s", $secs + 0);
}

sub _disk_bench_extract_iops {
    my ($txt) = @_;
    return '' unless defined $txt;
    if ($txt =~ /\biops\s*=\s*([0-9]+(?:\.[0-9]+)?[kKmM]?)\b/i) {
        return uc($1);
    }
    if ($txt =~ /\bIOPS=([0-9]+(?:\.[0-9]+)?[kKmM]?)\b/) {
        return uc($1);
    }
    return '';
}

sub parse_disk_benchmark_results {
    my ($txt, $profiles) = @_;
    return ([], {}) unless defined $txt && length $txt;
    $profiles ||= {};

    my %meta = (
        device   => '',
        profile  => '',
        duration => '',
        size     => '',
        iodepth  => '',
    );
    my @rows;
    my %seen;
    my @diskinfo_fields;
    my @transfer_rows;
    my @seek_rows;
    my @overhead_rows;
    my @fio_latency_rows;
    my $fio_current_kind = '';
    my %diskinfo_labels = (
        'sectorsize'                     => 'Sector size',
        'mediasize in bytes'             => 'Media size (bytes)',
        'mediasize in sectors'           => 'Media size (sectors)',
        'stripesize'                     => 'Stripe size',
        'stripeoffset'                   => 'Stripe offset',
        'cylinders according to firmware.' => 'Cylinders (firmware)',
        'heads according to firmware.'   => 'Heads (firmware)',
        'sectors according to firmware.' => 'Sectors (firmware)',
        'disk descr.'                    => 'Disk description',
        'disk ident.'                    => 'Disk identifier',
        'attachment'                     => 'Attachment',
        'trim/unmap support'             => 'TRIM/UNMAP',
        'rotation rate in rpm'           => 'Rotation rate (RPM)',
        'zone mode'                      => 'Zone mode',
    );

    for my $line (split /\n/, $txt) {
        $line =~ s/\r$//;
        $line =~ s/^\[[0-9:\-\s]+\]\s*//;
        $line =~ s/^\s+|\s+$//g;
        next if $line eq '';

        if ($line =~ /^Device\s*:\s*(.+)$/i) {
            $meta{device} = $1;
            next;
        }
        if ($line =~ /^Profile\s*:\s*([A-Za-z0-9_.\-]+)$/i) {
            my $k = $1;
            $meta{profile} = (ref($profiles->{$k}) eq 'HASH' && $profiles->{$k}{label})
                ? $profiles->{$k}{label}
                : $k;
            next;
        }
        if ($line =~ /^Duration\s*:\s*(.+)$/i) {
            $meta{duration} = $1;
            next;
        }
        if ($line =~ /^Size\s*:\s*(.+)$/i) {
            $meta{size} = $1;
            next;
        }
        if ($line =~ /^I\/O depth\s*:\s*(.+)$/i) {
            $meta{iodepth} = $1;
            next;
        }
        if ($line =~ /^(.*?)\s*#\s*(.+)$/) {
            my ($val, $key) = ($1, $2);
            $val =~ s/\s+$//;
            $key =~ s/\s+$//;
            next if $val eq '' || $key eq '';
            my $lk = lc($key);
            my $label = $diskinfo_labels{$lk} || $key;
            push @diskinfo_fields, { label => $label, value => $val };
            next;
        }

        if ($line =~ /^(read|write)\s*:\s*(.+)$/i) {
            my ($kind, $rest) = (lc($1), $2);
            $fio_current_kind = $kind;
            my ($rate_tok) = ($rest =~ /\b(?:bw|BW)\s*=\s*([0-9]+(?:\.[0-9]+)?\s*[KMGT]?i?B\/s)\b/);
            next unless defined $rate_tok && $rate_tok ne '';
            $rate_tok =~ s/\s+//g;
            my $mib = _disk_bench_rate_to_mib($rate_tok);
            next unless defined $mib;

            my $secs = '';
            if ($rest =~ /\brunt\s*=\s*(\d+)\s*msec\b/i) {
                $secs = _disk_bench_secs_human(($1 + 0) / 1000);
            }
            my $iops = _disk_bench_extract_iops($rest);
            my $key = "fio:$kind";
            next if $seen{$key}++;
            push @rows, {
                label      => ucfirst($kind),
                throughput => $rate_tok,
                duration   => $secs,
                iops       => $iops,
                mib        => $mib,
                color      => $kind eq 'write' ? '#f0ad4e' : '#0275d8',
            };
            next;
        }
        if ($fio_current_kind ne '' &&
            $line =~ /^(slat|clat|lat)\s*\(([^)]+)\)\s*:\s*min=([0-9]+(?:\.[0-9]+)?),\s*max=([0-9]+(?:\.[0-9]+)?),\s*avg=([0-9]+(?:\.[0-9]+)?)/i) {
            push @fio_latency_rows, {
                op     => ucfirst($fio_current_kind),
                metric => lc($1),
                unit   => $2,
                min    => $3,
                max    => $4,
                avg    => $5,
            };
            next;
        }

        if ($line =~ /([0-9]+(?:\.[0-9]+)?)\s*(?:bytes\/sec|bytes\/second|bytes per second)/i) {
            my $bps = $1;
            my $mib = _disk_bench_rate_to_mib($bps);
            next unless defined $mib;
            my $throughput = sprintf("%.1f MiB/s", $mib);
            next if $seen{'diskinfo:read'}++;
            push @rows, {
                label      => "Read",
                throughput => $throughput,
                duration   => '',
                iops       => '',
                mib        => $mib,
                color      => '#0275d8',
            };
            next;
        }
        if ($line =~ /^(outside|middle|inside)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*kbytes\s+in\s+([0-9]+(?:\.[0-9]+)?)\s*sec\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(kbytes\/sec|mbytes\/sec|gbytes\/sec)/i) {
            my ($zone, $kbytes, $sec, $rate_val, $rate_unit) = (lc($1), $2 + 0, $3 + 0, $4, lc($5));
            my $mib = _disk_bench_rate_to_mib("$rate_val $rate_unit");
            next unless defined $mib;
            my $throughput = sprintf("%.1f MiB/s", $mib);
            my $zlabel = ucfirst($zone);
            my $key = "diskinfo:$zone";
            next if $seen{$key}++;
            my $data_mib = $kbytes / 1024;
            push @transfer_rows, {
                zone       => $zlabel,
                data_size  => sprintf("%.0f KiB (%.1f MiB)", $kbytes, $data_mib),
                elapsed    => _disk_bench_secs_human($sec),
                throughput => $throughput,
                mib        => $mib,
            };
            push @rows, {
                label      => $zlabel,
                throughput => $throughput,
                data_size  => sprintf("%.0f KiB (%.1f MiB)", $kbytes, $data_mib),
                elapsed    => _disk_bench_secs_human($sec),
                duration   => '',
                iops       => '',
                mib        => $mib,
                color      => $zone eq 'outside' ? '#0275d8' : $zone eq 'middle' ? '#5cb85c' : '#f0ad4e',
            };
            next;
        }
        if ($line =~ /^([A-Za-z][A-Za-z\s]+):\s*(\d+)\s*iter\s*in\s*([0-9]+(?:\.[0-9]+)?)\s*sec\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*msec/i) {
            my $iter = $2 + 0;
            my $total_sec = $3 + 0;
            my $avg_ms = $4 + 0;
            push @seek_rows, {
                pattern   => $1,
                iter      => $iter,
                total_sec => _disk_bench_secs_human($total_sec),
                total_sec_raw => $total_sec,
                avg_msec  => sprintf("%.3f ms", $avg_ms),
                avg_msec_raw => $avg_ms,
            };
            next;
        }
        if ($line =~ /^time to read\s+(.+?)\s+([0-9]+(?:\.[0-9]+)?)\s*sec\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*msec\/sector/i) {
            push @overhead_rows, {
                metric    => "Read $1",
                total_sec => _disk_bench_secs_human($2),
                avg_msec  => sprintf("%.3f ms/sector", $3 + 0),
            };
            next;
        }
        if ($line =~ /^calculated command overhead\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*msec\/sector/i) {
            push @overhead_rows, {
                metric    => "Calculated overhead",
                total_sec => '-',
                avg_msec  => sprintf("%.3f ms/sector", $1 + 0),
            };
            next;
        }
    }

    $meta{diskinfo_fields} = \@diskinfo_fields;
    $meta{transfer_rates} = \@transfer_rows;
    $meta{seek_times} = \@seek_rows;
    $meta{command_overhead} = \@overhead_rows;
    $meta{fio_latency} = \@fio_latency_rows;
    return (\@rows, \%meta);
}

sub render_disk_benchmark_chart {
    my ($rows) = @_;
    return '' unless ref($rows) eq 'ARRAY' && @$rows;
    my $max_mib = 0;
    for my $r (@$rows) {
        my $v = $r->{mib};
        $max_mib = $v if defined $v && $v > $max_mib;
    }
    $max_mib = 1 if $max_mib <= 0;

    my $has_duration = 0;
    my $has_iops = 0;
    my $has_data_size = 0;
    my $has_elapsed = 0;
    for my $r (@$rows) {
        $has_duration = 1 if defined($r->{duration}) && $r->{duration} ne '';
        $has_iops = 1 if defined($r->{iops}) && $r->{iops} ne '';
        $has_data_size = 1 if defined($r->{data_size}) && $r->{data_size} ne '';
        $has_elapsed = 1 if defined($r->{elapsed}) && $r->{elapsed} ne '';
    }
    my $cols = "170px 1fr 110px";
    $cols .= " 180px" if $has_data_size;
    $cols .= " 100px" if $has_elapsed;
    $cols .= " 90px" if $has_iops;
    $cols .= " 100px" if $has_duration;

    my $html = "<div style='max-width:980px;border:1px solid #d7dbe0;border-radius:6px;padding:12px;background:#f7fafc'>";
    $html .= "<div style='display:grid;grid-template-columns:$cols;gap:10px;align-items:center;margin:0 0 8px 0;font-weight:600;color:#5f6b7a'>";
    $html .= "<div>" . &html_escape(L("COL_BENCH_METRIC")) . "</div>";
    $html .= "<div></div>";
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_THROUGHPUT")) . "</div>";
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_DATA")) . "</div>" if $has_data_size;
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_ELAPSED")) . "</div>" if $has_elapsed;
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_IOPS")) . "</div>" if $has_iops;
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_DURATION")) . "</div>" if $has_duration;
    $html .= "</div>";
    for my $r (@$rows) {
        my $v = $r->{mib} || 0;
        my $pct = int(($v / $max_mib) * 100);
        $pct = 1 if $v > 0 && $pct < 1;
        my $label = &html_escape($r->{label} || '');
        my $thr = &html_escape($r->{throughput} || '');
        my $data_size = &html_escape($r->{data_size} || '');
        my $elapsed = &html_escape($r->{elapsed} || '');
        my $dur = &html_escape($r->{duration} || '');
        my $iops = &html_escape($r->{iops} || '');
        my $color = $r->{color} || '#0275d8';
        my $title = sprintf("%.1f MiB/s", $v);
        $html .= "<div style='display:grid;grid-template-columns:$cols;gap:10px;align-items:center;margin:6px 0'>";
        $html .= "<div>$label</div>";
        $html .= "<div style='height:16px;background:#e7edf3;border-radius:3px;overflow:hidden'>"
              .  "<div title='" . &html_escape($title) . "' style='height:100%;width:${pct}%;background:$color'></div>"
              .  "</div>";
        $html .= "<div style='text-align:right;font-weight:600'>$thr</div>";
        $html .= "<div style='text-align:right;color:#5f6b7a'>" . ($data_size ne '' ? $data_size : '-') . "</div>" if $has_data_size;
        $html .= "<div style='text-align:right;color:#5f6b7a'>" . ($elapsed ne '' ? $elapsed : '-') . "</div>" if $has_elapsed;
        $html .= "<div style='text-align:right;color:#5f6b7a'>" . ($iops ne '' ? $iops : '-') . "</div>" if $has_iops;
        $html .= "<div style='text-align:right;color:#5f6b7a'>" . ($dur ne '' ? $dur : '-') . "</div>" if $has_duration;
        $html .= "</div>";
    }
    $html .= "</div>";
    return $html;
}

sub render_disk_seek_times_chart {
    my ($rows) = @_;
    return '' unless ref($rows) eq 'ARRAY' && @$rows;
    my @vals = grep { defined($_) && $_ > 0 } map { $_->{avg_msec_raw} } @$rows;
    return '' unless @vals;

    my ($best) = sort { $a <=> $b } @vals;
    my ($worst) = sort { $b <=> $a } @vals;
    my $span = $worst - $best;
    my $html = "<div style='height:8px'></div>";
    $html .= "<p>" . &html_escape(L("MSG_DISK_BENCH_SEEK_CHART_NOTE")) . "</p>";
    $html .= "<div style='max-width:980px;border:1px solid #d7dbe0;border-radius:6px;padding:12px;background:#f7fafc'>";
    $html .= "<div style='display:grid;grid-template-columns:220px 1fr 100px 90px 110px;gap:10px;align-items:center;margin:0 0 8px 0;font-weight:600;color:#5f6b7a'>";
    $html .= "<div>" . &html_escape(L("COL_BENCH_METRIC")) . "</div>";
    $html .= "<div></div>";
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_AVG")) . "</div>";
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_ITER")) . "</div>";
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_ELAPSED")) . "</div>";
    $html .= "</div>";
    for my $r (@$rows) {
        my $v = $r->{avg_msec_raw};
        next unless defined $v && $v > 0;
        my $pct = $span > 0 ? int((($worst - $v) / $span) * 100) : 100;
        $pct = 4 if $pct < 4;
        my $label = &html_escape($r->{pattern} || '');
        my $avg = &html_escape($r->{avg_msec} || '');
        my $iter = &html_escape(defined($r->{iter}) ? $r->{iter} : '');
        my $elapsed = &html_escape($r->{total_sec} || '');
        my $tip = &html_escape("iter=$iter, elapsed=$elapsed");
        my $color = '#5bc0de';
        $color = '#5cb85c' if $v <= $best + (($span > 0 ? $span : $best) * 0.2);
        $color = '#f0ad4e' if $v >= $best + (($span > 0 ? $span : $best) * 0.7);
        $html .= "<div style='display:grid;grid-template-columns:220px 1fr 100px 90px 110px;gap:10px;align-items:center;margin:6px 0'>";
        $html .= "<div>$label</div>";
        $html .= "<div style='height:16px;background:#e7edf3;border-radius:3px;overflow:hidden'>"
              .  "<div title='$tip' style='height:100%;width:${pct}%;background:$color'></div>"
              .  "</div>";
        $html .= "<div style='text-align:right;font-weight:600'>$avg</div>";
        $html .= "<div style='text-align:right;color:#5f6b7a'>$iter</div>";
        $html .= "<div style='text-align:right;color:#5f6b7a'>$elapsed</div>";
        $html .= "</div>";
    }
    $html .= "</div>";
    return $html;
}

sub render_disk_benchmark_details {
    my ($meta) = @_;
    return '' unless ref($meta) eq 'HASH';
    my $html = '';

    if (ref($meta->{transfer_rates}) eq 'ARRAY' && @{$meta->{transfer_rates}}) {
        my @mibs = grep { defined($_) && $_ >= 0 } map { $_->{mib} } @{ $meta->{transfer_rates} };
        if (@mibs) {
            my $sum = 0;
            $sum += $_ for @mibs;
            my $avg = $sum / scalar(@mibs);
            my ($best) = sort { ($b->{mib} || 0) <=> ($a->{mib} || 0) } @{ $meta->{transfer_rates} };
            my ($worst) = sort { ($a->{mib} || 0) <=> ($b->{mib} || 0) } @{ $meta->{transfer_rates} };
            my $avg_txt = sprintf("%.1f MiB/s", $avg);
            my $best_txt = ($best ? ($best->{zone} . " (" . $best->{throughput} . ")") : '-');
            my $worst_txt = ($worst ? ($worst->{zone} . " (" . $worst->{throughput} . ")") : '-');
            $html .= "<p><b>" . &html_escape(L("LBL_DISK_BENCH_TRANSFER_SUMMARY")) . ":</b> "
                . &html_escape(L("MSG_DISK_BENCH_TRANSFER_SUMMARY", $avg_txt, $best_txt, $worst_txt)) . "</p>";
        }
    }

    if (ref($meta->{seek_times}) eq 'ARRAY' && @{$meta->{seek_times}}) {
        $html .= render_disk_seek_times_chart($meta->{seek_times});
    }

    if (ref($meta->{command_overhead}) eq 'ARRAY' && @{$meta->{command_overhead}}) {
        my @heads = (
            L("COL_BENCH_METRIC"),
            L("COL_BENCH_ELAPSED"),
            L("COL_BENCH_AVG"),
        );
        my @rows = map {
            [
                &html_escape($_->{metric} || ''),
                &html_escape($_->{total_sec} || ''),
                &html_escape($_->{avg_msec} || ''),
            ]
        } @{ $meta->{command_overhead} };
        $html .= &ui_columns_table(\@heads, 100, \@rows, undef, 1, L("TABLE_DISK_BENCH_COMMAND_OVERHEAD"), L("VALUE_NONE"));
    }

    if (ref($meta->{fio_latency}) eq 'ARRAY' && @{$meta->{fio_latency}}) {
        my @heads = (
            L("COL_BENCH_OPERATION"),
            L("COL_BENCH_METRIC"),
            L("COL_BENCH_MIN"),
            L("COL_BENCH_AVG"),
            L("COL_BENCH_MAX"),
        );
        my @rows = map {
            [
                &html_escape($_->{op} || ''),
                &html_escape(uc($_->{metric} || '')),
                &html_escape($_->{min} . " " . ($_->{unit} || '')),
                &html_escape($_->{avg} . " " . ($_->{unit} || '')),
                &html_escape($_->{max} . " " . ($_->{unit} || '')),
            ]
        } @{ $meta->{fio_latency} };
        $html .= &ui_columns_table(\@heads, 100, \@rows, undef, 1, L("TABLE_DISK_BENCH_FIO_LATENCY"), L("VALUE_NONE"));
    }

    if (ref($meta->{diskinfo_fields}) eq 'ARRAY' && @{$meta->{diskinfo_fields}}) {
        my @heads = (
            L("COL_BENCH_METRIC"),
            L("COL_DISK_BENCH_VALUE"),
        );
        my @rows = map {
            [
                &html_escape($_->{label} || ''),
                &html_escape($_->{value} || ''),
            ]
        } @{ $meta->{diskinfo_fields} };
        $html .= &ui_columns_table(\@heads, 100, \@rows, undef, 1, L("TABLE_DISK_BENCH_DEVICE_INFO"), L("VALUE_NONE"));
    }

    return $html;
}

sub action_benchmark {
    if (!cfg_bool('enable_benchmarking', 0)) {
        print &ui_print_error(L("ERR_BENCHMARKING_DISABLED"));
        return;
    }

    my $profiles = disk_benchmark_profiles();
    my $bench_do = $in{'bench_do'} || '';
    if ($bench_do eq 'job_log') {
        my $job = $in{'job'} || '';
        if ($job !~ /^diskbench_[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_DISK_BENCH_LOG_INVALID"));
            return;
        }
        my $txt = zfsguru_read_job_log(file => $job);
        if (!length $txt) {
            print &ui_print_error(L("ERR_DISK_BENCH_LOG_NOT_FOUND"));
            return;
        }
        print &ui_subheading(L("SUB_DISK_BENCH_LOG", $job));
        print "<pre>" . &html_escape($txt || '') . "</pre>";
        print "<p><a class='button' href='disks.cgi?action=benchmark'>" . L("BTN_BACK") . "</a></p>";
        return;
    }
    if ($bench_do eq 'job_results') {
        my $job = $in{'job'} || '';
        if ($job !~ /^diskbench_[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_DISK_BENCH_LOG_INVALID"));
            return;
        }
        my $txt = zfsguru_read_job_log(file => $job);
        if (!length $txt) {
            print &ui_print_error(L("ERR_DISK_BENCH_LOG_NOT_FOUND"));
            return;
        }
        my ($rows, $meta) = parse_disk_benchmark_results($txt, $profiles);
        print &ui_subheading(L("SUB_DISK_BENCH_RESULTS", $job));
        if (!$rows || !@$rows) {
            print &ui_print_error(L("ERR_DISK_BENCH_RESULTS_NOT_FOUND"));
        } else {
            print "<p>" . L("MSG_DISK_BENCH_RESULTS_NOTE") . "</p>";
            print "<p><b>" . &html_escape(L("ROW_DISK_NAME")) . ":</b> " . &html_escape($meta->{device} || '-') . "</p>" if $meta->{device};
            print "<p><b>" . &html_escape(L("ROW_BENCH_PROFILE")) . ":</b> " . &html_escape($meta->{profile} || '-') . "</p>" if $meta->{profile};
            print "<p><b>" . &html_escape(L("ROW_BENCH_DURATION")) . ":</b> " . &html_escape($meta->{duration} || '-') . "</p>" if $meta->{duration};
            print "<p><b>" . &html_escape(L("ROW_BENCH_SIZE_MIB")) . ":</b> " . &html_escape($meta->{size} || '-') . "</p>" if $meta->{size};
            print "<p><b>" . &html_escape(L("ROW_BENCH_IODEPTH")) . ":</b> " . &html_escape($meta->{iodepth} || '-') . "</p>" if $meta->{iodepth};
            print render_disk_benchmark_chart($rows);
            print render_disk_benchmark_details($meta);
        }
        my $log_link = "disks.cgi?action=job_log&job=" . &url_encode($job);
        print "<p>";
        print &ui_link_icon($log_link, L("BTN_VIEW_LOG"), undef, { class => 'primary' });
        print " ";
        print "<a class='button' href='disks.cgi?action=benchmark'>" . L("BTN_BACK") . "</a>";
        print "</p>";
        return;
    }

    my $profile = $in{'bench_profile'} || 'quick_read';
    $profile = 'quick_read' unless exists $profiles->{$profile};

    my $duration = $in{'bench_duration'};
    $duration = 20 if !defined $duration || $duration !~ /^\d+$/;
    my $size_mib = $in{'bench_size_mib'};
    $size_mib = 1024 if !defined $size_mib || $size_mib !~ /^\d+$/;
    my $iodepth = $in{'bench_iodepth'};
    $iodepth = 8 if !defined $iodepth || $iodepth !~ /^\d+$/;

    if ($in{'kill_bg_job'}) {
        my $job = $in{'kill_bg_job'} || '';
        if ($job !~ /^diskbench_[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_DISK_BENCH_LOG_INVALID"));
        } else {
            my ($ok, $msg) = zfsguru_kill_job(file => $job);
            if ($ok) {
                print &ui_print_success(L("SUCCESS_WIPE_JOB_KILLED", $job));
            } else {
                print &ui_print_error(L("ERR_WIPE_JOB_KILL_FAILED", $msg || 'kill failed'));
            }
        }
    }

    if ($in{'clear_bg_logs'}) {
        my ($ok, $err, $count) = zfsguru_clear_job_logs(prefix => 'diskbench');
        if ($ok) {
            print &ui_print_success(L("SUCCESS_BG_LOGS_CLEARED", $count));
        } else {
            print &ui_print_error(L("ERR_BG_LOGS_CLEAR_FAILED", $err || 'clear failed'));
        }
    }

    if ($in{'run_benchmark'}) {
        my $disk = $in{'disk'} || '';
        my %diskset = map { $_ => 1 } @{ disk_list() || [] };

        if (!$disk || !$diskset{$disk}) {
            print &ui_print_error(L("ERR_BENCHMARK_NO_DISK"));
        }
        elsif (!exists $profiles->{$profile}) {
            print &ui_print_error(L("ERR_DISK_BENCH_PROFILE_INVALID"));
        }
        elsif ($duration < 5 || $duration > 600) {
            print &ui_print_error(L("ERR_DISK_BENCH_DURATION_INVALID"));
        }
        elsif ($size_mib < 16 || $size_mib > 1048576) {
            print &ui_print_error(L("ERR_DISK_BENCH_SIZE_INVALID"));
        }
        elsif ($iodepth < 1 || $iodepth > 64) {
            print &ui_print_error(L("ERR_DISK_BENCH_IODEPTH_INVALID"));
        }
        elsif (!$in{'confirm_benchmark'}) {
            print &ui_alert(L("MSG_BENCHMARK_WARNING"), 'warning');
            print &ui_print_error(L("ERR_DISK_BENCH_CONFIRM_REQUIRED"));
        }
        elsif ($profiles->{$profile}{destructive} && !$in{'confirm_benchmark_destructive'}) {
            print &ui_alert(L("WARN_DISK_BENCH_DESTRUCTIVE"), 'warning');
            print &ui_print_error(L("ERR_DISK_BENCH_CONFIRM_DESTRUCTIVE_REQUIRED"));
        }
        else {
            my $title = L("JOB_TITLE_DISK_BENCH", $disk);
            my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                prefix => 'diskbench',
                title  => $title,
                run    => sub {
                    disk_benchmark_job(
                        disk     => $disk,
                        profile  => $profile,
                        duration => $duration,
                        size_mib => $size_mib,
                        iodepth  => $iodepth,
                    );
                },
                env    => { PAGER => 'cat' },
            );

            if (!$ok) {
                print &ui_print_error(L("ERR_DISK_BENCH_JOB_START_FAILED", $err));
            } else {
                my $link = "disks.cgi?action=job_log&job=" . &url_encode($log_file);
                print &ui_print_success(L("SUCCESS_DISK_BENCH_JOB_STARTED", $job_id) . " " .
                    "<a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" . &html_escape($link) . "'>" . &html_escape(L("BTN_VIEW_LOG")) . "</a>");
            }
        }
    }

    print &ui_subheading(L("SUB_DISK_BENCHMARK"));
    print "<p>" . L("MSG_BENCHMARK_WARNING") . "</p>";
    print &ui_alert(L("WARN_DISK_BENCH_DESTRUCTIVE"), "warning");

    my $fio = $config{'fio_cmd'} || '/usr/local/bin/fio';
    if (!command_exists($fio)) {
        print &ui_alert(L("WARN_DISK_BENCH_FIO_MISSING", $fio), "info");
    }

    my $disks = disk_list();
    my @disk_opts = map { [ $_, $_ ] } @{ $disks || [] };
    my @profile_opts = map { [ $_, $profiles->{$_}{label} ] } qw(
        quick_read seq_read rand_read seq_write rand_write
    );

    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "benchmark");
    print &ui_hidden("run_benchmark", 1);

    print &ui_table_start(L("TABLE_BENCHMARK_CONFIG"), "width=100%", 2);
    print &ui_table_row(L("COL_DISK"), &ui_select("disk", ($in{'disk'} || ''), \@disk_opts));
    print &ui_table_row(L("ROW_BENCH_PROFILE"), &ui_select("bench_profile", $profile, \@profile_opts));
    print &ui_table_row(L("ROW_BENCH_DURATION"), &ui_textbox("bench_duration", $duration, 8) . " s");
    print &ui_table_row(L("ROW_BENCH_SIZE_MIB"), &ui_textbox("bench_size_mib", $size_mib, 10) . " MiB");
    print &ui_table_row(L("ROW_BENCH_IODEPTH"), &ui_textbox("bench_iodepth", $iodepth, 6));
    print &ui_table_row(
        L("ROW_CONFIRM"),
        &ui_checkbox("confirm_benchmark", 1, L("LBL_CONFIRM_DISK_BENCHMARK"), 0)
    );
    print &ui_table_row(
        L("ROW_CONFIRM_DESTRUCTIVE"),
        &ui_checkbox("confirm_benchmark_destructive", 1, L("LBL_CONFIRM_DISK_BENCHMARK_DESTRUCTIVE"), 0)
    );
    print &ui_table_end();
    print &ui_form_end([ [ "run_benchmark", L("BTN_RUN_BENCHMARK") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_DISK_BENCHMARK_JOBS"));
    print "<p>" . L("MSG_DISK_BENCH_JOBS") . "</p>";
    my $jobs = zfsguru_list_jobs(prefix => 'diskbench', limit => 25);
    my @heads = (L("COL_JOB"), L("COL_STATUS"), L("COL_UPDATED"), L("COL_ACTIONS"));
    my @data;
    for my $j (@{ $jobs || [] }) {
        my $f = $j->{file} || next;
        my $raw_st = ($j->{status} || '');
        my $st = $raw_st eq 'ok' ? L("VALUE_JOB_DONE")
            : $raw_st eq 'failed' ? L("VALUE_JOB_FAILED")
            : $raw_st eq 'killed' ? L("VALUE_JOB_KILLED")
            : $raw_st eq 'stale' ? L("VALUE_JOB_STALE")
            : L("VALUE_JOB_RUNNING");
        my $st_class =
            $st eq L("VALUE_JOB_DONE")    ? 'zfsguru-status-ok' :
            $st eq L("VALUE_JOB_FAILED")  ? 'zfsguru-status-bad' :
            $st eq L("VALUE_JOB_KILLED")  ? 'zfsguru-status-bad' :
            $st eq L("VALUE_JOB_STALE")   ? 'zfsguru-status-warn' :
            $st eq L("VALUE_JOB_RUNNING") ? 'zfsguru-status-warn' :
                                            'zfsguru-status-unknown';
        my $view = "disks.cgi?action=job_log&job=" . &url_encode($f);
        my $view_btn = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_VIEW_LOG"))
                     . "' onclick=\"window.location.href='" . &html_escape($view)
                     . "'\" style='background:#0275d8;color:#fff;border-color:#0275d8'>";
        my $results_btn = '';
        if ($raw_st eq 'ok') {
            my $results = "disks.cgi?action=benchmark&bench_do=job_results&job=" . &url_encode($f);
            $results_btn = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_VIEW_RESULTS"))
                         . "' onclick=\"window.location.href='" . &html_escape($results)
                         . "'\" style='margin-left:6px;background:#5cb85c;color:#fff;border-color:#4cae4c'>";
        }
        my $kill_btn = '';
        if ($raw_st eq 'running') {
            $kill_btn = "<form method='post' action='disks.cgi' style='display:inline;margin-left:6px'>"
                      . &ui_hidden("action", "benchmark")
                      . &ui_hidden("kill_bg_job", $f)
                      . "<input type='submit' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                      . "' style='background:#d9534f;color:#fff;border-color:#d9534f'>"
                      . "</form>";
        } else {
            $kill_btn = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                      . "' disabled='disabled' title='" . &html_escape(L("MSG_JOB_NOT_RUNNING"))
                      . "' style='margin-left:6px;background:#d9534f;color:#fff;border-color:#d9534f;opacity:.45;cursor:not-allowed'>";
        }
        push @data, [
            &html_escape($f),
            "<span class='$st_class'>" . &html_escape($st) . "</span>",
            &html_escape($j->{mtime} || ''),
            $view_btn . $results_btn . $kill_btn,
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, undef, L("VALUE_NONE"));
    print "<p>";
    print &ui_link_icon("disks.cgi?action=benchmark", L("BTN_REFRESH"), undef, { class => 'primary' });
    print " ";
    print &ui_form_start("disks.cgi", "post", "style='display:inline'");
    print &ui_hidden("action", "benchmark");
    print &ui_form_end([
        [ "clear_bg_logs", L("BTN_EMPTY_LOGS"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ],
    ]);
    print "</p>";
}

sub action_monitor {
    print &ui_subheading(L("SUB_IO_MONITOR"));

    my $filter = defined $in{'filter'} ? $in{'filter'} : '';
    $filter = '^(gpt|label)/' if $filter eq '';

    my $mode = '';
    if ($filter eq '-a' || $filter eq '-all') {
        $mode = $filter;
    } else {
        if (length($filter) > 128 || $filter !~ /^[A-Za-z0-9_\-\.\^\$\|\(\)\/\+\*\?\[\]\\:]+$/) {
            $filter = '^(gpt|label)/';
            print &ui_print_error(L("ERR_MONITOR_FILTER_INVALID"));
        }
    }

    my $auto = $in{'norefresh'} ? 0 : 1;
    my $interval = 2;

    my $canon_filter = ($mode eq '-a' || $mode eq '-all') ? $mode : $filter;
    my $base_link = "disks.cgi?action=monitor&filter=" . &url_encode($canon_filter);
    my $state_qs  = $auto ? '' : '&norefresh=1';
    my $view_formatted = "disks.cgi?action=monitor&filter=" . &url_encode('^(gpt|label)/') . $state_qs;
    my $view_active    = "disks.cgi?action=monitor&filter=-a" . $state_qs;
    my $view_all       = "disks.cgi?action=monitor&filter=-all" . $state_qs;
    my $refresh_link   = $base_link . $state_qs;
    my $start_link     = $base_link;
    my $stop_link      = $base_link . "&norefresh=1";

    if ($auto) {
        my $refresh_js = ui_page_refresh();
        print "<script>setTimeout(function(){ $refresh_js; }, " . ($interval * 1000) . ");</script>";
    }

    my ($rc, $out, $err);
    if ($mode eq '-a') {
        ($rc, $out, $err) = run_cmd($zfsguru_lib::GSTAT || '/usr/sbin/gstat', '-b', '-a');
    } elsif ($mode eq '-all') {
        ($rc, $out, $err) = run_cmd($zfsguru_lib::GSTAT || '/usr/sbin/gstat', '-b');
    } else {
        ($rc, $out, $err) = run_cmd($zfsguru_lib::GSTAT || '/usr/sbin/gstat', '-b', '-f', $filter);
    }

    print &ui_form_start("disks.cgi", "get");
    print &ui_hidden("action", "monitor");
    print &ui_hidden("norefresh", "1") if !$auto;
    print &ui_table_start(L("TABLE_IO_MONITOR_FILTER"), "width=100%", 2);
    print &ui_table_row(L("ROW_MONITOR_FILTER"), &ui_textbox("filter", $filter, 40));
    print &ui_table_end();
    print &ui_form_end([ [ "apply", L("BTN_APPLY_FILTER") ] ]);

    print &ui_table_start("Quick Actions", "width=100%", 2);
    print &ui_table_row("Filter Presets",
        &ui_link_icon($view_formatted, L("BTN_MONITOR_FORMATTED"), undef, { class => 'default' }) . " " .
        &ui_link_icon($view_active, L("BTN_MONITOR_ACTIVE"), undef, { class => 'default' }) . " " .
        &ui_link_icon($view_all, L("BTN_MONITOR_ALL"), undef, { class => 'default' })
    );
    print &ui_table_row("Refresh Controls",
        &ui_link_icon($refresh_link, L("BTN_REFRESH"), undef, { class => 'primary' }) . " " .
        ($auto
            ? &ui_link_icon($stop_link, L("BTN_STOP_REFRESH"), undef, { class => 'danger' })
            : &ui_link_icon($start_link, L("BTN_START_REFRESH"), undef, { class => 'default' }))
    );
    print &ui_table_row("Auto Refresh Status",
        $auto ? "Running (every ${interval}s)" : "Stopped");
    print &ui_table_end();

    if ($rc != 0) {
        print &ui_print_error(L("ERR_GSTAT_FAILED", $err || 'gstat failed'));
    }
    print "<pre>" . &html_escape($out || '') . "</pre>";
}

sub action_memory {
    print &ui_subheading(L("SUB_MEMORY_DISKS"));

    my $load_mds = sub {
        my $raw_mds = mdconfig_list();
        $raw_mds = [] if ref($raw_mds) ne 'ARRAY';
        my @mds_norm;
        my %by_unit_idx;
        for my $e (@$raw_mds) {
            if (ref($e) eq 'HASH') {
                my %h = %$e;
                if (!defined($h{unit}) || $h{unit} !~ /^\d+$/) {
                    my $name = $h{device} // $h{name} // '';
                    $name =~ s{^/dev/}{};
                    $h{unit} = $1 if $name =~ /^md(\d+)$/;
                }
                my $dev = $h{device} // '';
                if (!$dev) {
                    my $u = defined($h{unit}) ? $h{unit} : '';
                    $dev = ($u ne '' && $u =~ /^\d+$/) ? "/dev/md$u" : '';
                }
                $h{device} = $dev if $dev ne '';
                $h{size} = '-' if !defined($h{size}) || $h{size} eq '';
                $h{type} = '-' if !defined($h{type}) || $h{type} eq '';
                $h{file} = '' if !defined($h{file});
                push @mds_norm, \%h;
                $by_unit_idx{$h{unit}} = $#mds_norm if defined($h{unit}) && $h{unit} =~ /^\d+$/;
                next;
            }
            my $name = "$e";
            $name =~ s/^\s+|\s+$//g;
            next if $name eq '';
            $name =~ s{^/dev/}{};
            my $unit = '';
            if ($name =~ /^md(\d+)$/) {
                $unit = $1;
            } elsif ($name =~ /^(\d+)$/) {
                $unit = $1;
                $name = "md$unit";
            }
            my %h = (
                unit   => $unit,
                device => "/dev/$name",
                size   => '-',
                type   => '-',
                file   => '',
            );
            push @mds_norm, \%h;
            $by_unit_idx{$unit} = $#mds_norm if $unit ne '';
        }

        # Enrich normalized rows with mdconfig -lv details when available.
        my ($lv_rc, $lv_out, $lv_err) = run_cmd($zfsguru_lib::MD || '/sbin/mdconfig', '-lv');
        if ($lv_rc == 0 && defined $lv_out && $lv_out ne '') {
            for my $ln (split /\n/, $lv_out) {
                next unless $ln =~ /^\s*(md\d+)\s+(\S+)\s+(\S+)(?:\s+(.+))?$/;
                my ($mdn, $type, $size, $back) = ($1, $2, $3, $4 // '');
                next unless $mdn =~ /^md(\d+)$/;
                my $u = $1;
                my %h = (
                    unit   => $u,
                    device => "/dev/$mdn",
                    type   => $type || '-',
                    size   => $size || '-',
                    file   => $back,
                );
                if (exists $by_unit_idx{$u}) {
                    my $idx = $by_unit_idx{$u};
                    $mds_norm[$idx] = { %{ $mds_norm[$idx] }, %h };
                } else {
                    push @mds_norm, \%h;
                    $by_unit_idx{$u} = $#mds_norm;
                }
            }
        }

        my $mds = \@mds_norm;
        my %md_by_unit = map { (defined($_->{unit}) && $_->{unit} =~ /^\d+$/) ? ($_->{unit} => $_) : () } @$mds;
        return ($mds, \%md_by_unit);
    };

    my ($mds, $md_by_unit_ref) = $load_mds->();
    my %md_by_unit = %{$md_by_unit_ref || {}};

    if ($in{'destroy_md'}) {
        my $unit_in = defined($in{'md_destroy_unit'}) ? $in{'md_destroy_unit'} : '';
        my $unit = $unit_in;
        $unit =~ s/^\s+|\s+$//g;
        if ($unit =~ m{^/dev/md(\d+)$}i) {
            $unit = $1;
        } elsif ($unit =~ /^md(\d+)$/i) {
            $unit = $1;
        }
        if ($unit !~ /^\d+$/ || !exists $md_by_unit{$unit}) {
            print &ui_print_error(L("ERR_MD_UNIT_INVALID", $unit_in));
        } elsif (!$in{'confirm_destroy'}) {
            print &ui_print_error(L("ERR_CONFIRM_MD_DESTROY_REQUIRED"));
        } else {
            my $md = $md_by_unit{$unit};
            eval {
                my ($ok, $msg) = md_detach($unit);
                die $msg unless $ok;
                if ($md->{type} && $md->{type} eq 'vnode' && $in{'delete_backing'} && $md->{file}) {
                    unlink $md->{file};
                } elsif ($in{'delete_backing'}) {
                    print &ui_alert(L("MSG_MD_BACKING_UNKNOWN"), "info");
                }
                print &ui_print_success(L("SUCCESS_MD_DESTROYED", "md$unit"));
            };
            if ($@) {
                print &ui_print_error(L("ERR_MD_DESTROY_FAILED", $@));
            }
        }
    }

    if ($in{'create_md'}) {
        my $type = $in{'md_type'} || 'malloc';
        my $unit = $in{'md_unit'} || 'auto';
        my $size_val = $in{'md_size'} || '';
        my $size_unit = $in{'md_size_unit'} || 'M';
        my $size = $size_val . $size_unit;
        my $file = $in{'md_file'} || '';
        my $ro = $in{'md_readonly'} ? 1 : 0;

        if ($type !~ /^(malloc|vnode)$/) {
            print &ui_print_error(L("ERR_MD_TYPE_INVALID", $type));
        } elsif ($type eq 'vnode' && (!$file || $file !~ m{^/})) {
            print &ui_print_error(L("ERR_MD_FILE_REQUIRED"));
        } elsif ($type eq 'malloc' && !is_zfs_size($size)) {
            print &ui_print_error(L("ERR_MD_SIZE_INVALID", $size));
        } else {
            eval {
                if ($type eq 'vnode' && $file && !-e $file) {
                    my $bytes = parse_size_bytes($size);
                    die "Invalid size" unless $bytes;
                    my ($rc, $out, $err) = run_cmd($zfsguru_lib::DD || '/bin/dd',
                        'if=/dev/zero', "of=$file", 'bs=1', 'count=0', "seek=$bytes");
                    die $err || "dd failed" if $rc != 0;
                }

                my %opt = ( type => $type, ro => $ro );
                $opt{unit} = $unit if $unit ne 'auto';
                if ($type eq 'vnode') {
                    $opt{file} = $file;
                } else {
                    $opt{size} = $size;
                }
                my ($ok, $mddev) = md_attach(%opt);
                die $mddev unless $ok;
                print &ui_print_success(L("SUCCESS_MD_CREATED", $mddev || 'md'));
            };
            if ($@) {
                print &ui_print_error(L("ERR_MD_CREATE_FAILED", $@));
            }
        }
    }

    # Refresh md list after possible create/destroy so UI shows current units immediately.
    ($mds, $md_by_unit_ref) = $load_mds->();
    %md_by_unit = %{$md_by_unit_ref || {}};

    my @md_heads = (L("COL_DISK"), L("COL_SIZE"), L("COL_TYPE"), L("COL_BACKING"));
    my @md_data;
    if (@$mds) {
        for my $md (@$mds) {
            push @md_data, [
                &html_escape($md->{device}),
                &html_escape($md->{size} || '-'),
                &html_escape($md->{type} || '-'),
                &html_escape($md->{file} || '-'),
            ];
        }
    }
    print &ui_columns_table(\@md_heads, 100, \@md_data, undef, 1, undef, L("VALUE_NONE"));

    print &ui_hr();
    my @unit_opts = ( [ 'auto', L("VALUE_AUTO") ] );
    my %used = map { $_->{unit} => 1 } @$mds;
    for my $i (1 .. 255) {
        push @unit_opts, [ $i, $i ] unless $used{$i};
    }
    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "memory");
    print &ui_hidden("create_md", 1);
    print &ui_table_start(L("TABLE_CREATE_MD"), "width=100%", 2);
    print &ui_table_row(L("ROW_MD_UNIT"),
        &ui_select("md_unit", "auto", \@unit_opts) .
        "<br><small>" . L("HINT_MD_UNIT_CREATE") . "</small>");
    print &ui_table_row(L("ROW_MD_TYPE"), &ui_select("md_type", "malloc", [
        [ "malloc", L("OPT_MD_MALLOC") ],
        [ "vnode", L("OPT_MD_VNODE") ],
    ]) . "<br><small>" . L("HINT_MD_TYPE") . "</small>");
    print &ui_table_row(L("ROW_MD_SIZE"),
        &ui_textbox("md_size", "512", 8) . " " .
        &ui_select("md_size_unit", "M", [
            [ "K", "K" ],
            [ "M", "M" ],
            [ "G", "G" ],
            [ "T", "T" ],
        ]) .
        "<br><small>" . L("HINT_MD_SIZE") . "</small>"
    );
    print &ui_table_row(L("ROW_MD_FILE"),
        &ui_textbox("md_file", "", 50) .
        "<br><small>" . L("HINT_MD_FILE") . "</small>");
    print &ui_table_row(L("ROW_MD_READONLY"), &ui_checkbox("md_readonly", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "create_md", L("BTN_CREATE_MD") ] ]);

    print &ui_hr();
    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "memory");
    print &ui_hidden("destroy_md", 1);
    my @md_opts = map { [ $_->{unit}, $_->{device} ] } @$mds;
    my $destroy_unit_widget = @md_opts
        ? (&ui_select("md_destroy_unit", "", \@md_opts) . "<br><small>" . L("HINT_MD_DESTROY_UNIT") . "</small>")
        : ("<span class='zfsguru-muted'>" . L("MSG_MD_NO_UNIT_DETECTED_YET") . "</span>");
    print &ui_table_start(L("TABLE_DESTROY_MD"), "width=100%", 2);
    print &ui_table_row(L("ROW_MD_UNIT"), $destroy_unit_widget);
    print &ui_table_row(L("ROW_MD_DELETE_BACKING"), &ui_checkbox("delete_backing", 1, L("OPT_YES"), 0));
    print &ui_table_row(L("ROW_CONFIRM_DESTROY"), &ui_checkbox("confirm_destroy", 1, L("LBL_CONFIRM_DESTROY"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "destroy_md", L("BTN_DESTROY_MD"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ] ]);
}

sub action_query {
    my $disk_name = $in{'disk'} || '';
    if (!$disk_name || !is_disk_name($disk_name)) {
        print &ui_print_error(L("ERR_DISK_INVALID", $disk_name));
        return;
    }

    my @part_list = ();
    push @part_list, glob("/dev/${disk_name}p*");
    push @part_list, glob("/dev/${disk_name}s*");

    my @label_targets;
    for my $dir (qw(/dev/gpt /dev/label)) {
        next unless -d $dir;
        for my $path (glob("$dir/*")) {
            my $real = eval { realpath($path) } || '';
            next unless $real;
            if ($real =~ m{^/dev/\Q$disk_name\E}) {
                push @label_targets, $path;
            }
        }
    }

    my @targets = ("/dev/$disk_name", @part_list, @label_targets);
    my %seen_target;
    @targets = grep { !$seen_target{$_}++ } @targets;
    my %allowed_target = map { $_ => 1 } @targets;

    my $normalize_pmap = sub {
        my ($src) = @_;
        my $pmap = $src;
        if (ref($pmap) eq 'ARRAY') {
            my $di = diskinfo($disk_name) || {};
            my $sector_size = (defined $di->{sectorsize} && $di->{sectorsize} =~ /^\d+$/) ? int($di->{sectorsize}) : 512;
            my $gshow = gpart_show($disk_name) || '';
            my $scheme = 'UNKNOWN';
            $scheme = 'GPT' if $gshow =~ /\bGPT\b/i;
            $scheme = 'MBR' if $scheme eq 'UNKNOWN' && $gshow =~ /\bMBR\b/i;

            my %by_index;
            my @parts;
            for my $pi (@$pmap) {
                next unless ref($pi) eq 'HASH';
                my $idx = (defined $pi->{index} && $pi->{index} =~ /^\d+$/) ? int($pi->{index}) : undef;
                my $start = (defined $pi->{start} && $pi->{start} =~ /^\d+$/) ? int($pi->{start}) : undef;
                my $size = (defined $pi->{size} && $pi->{size} =~ /^\d+$/) ? int($pi->{size}) : undef;
                my $end = (defined $start && defined $size && $size > 0) ? ($start + $size - 1) : undef;
                my $name = $pi->{name} || '';
                my $seg = {
                    type       => 'partition',
                    scheme     => $scheme,
                    ptype      => ($pi->{type} || ''),
                    index      => $idx,
                    start      => $start,
                    end        => $end,
                    size       => $size,
                    size_bytes => (defined $size ? $size * $sector_size : undef),
                    name       => $name,
                    dev        => ($name ne '' ? "/dev/$name" : ''),
                    gpt_label  => normalize_label_value($pi->{label}),
                    mbr_active => 0,
                };
                push @parts, $seg;
                $by_index{$idx} = $seg if defined $idx;
            }
            my $total_sectors = (defined $di->{sectorcount} && $di->{sectorcount} =~ /^\d+$/)
                ? int($di->{sectorcount}) : 0;
            my $usable_start = 0;
            my $usable_end = ($total_sectors > 0) ? ($total_sectors - 1) : -1;
            if ($scheme eq 'GPT' && $total_sectors > 0) {
                # Keep GPT metadata and safety zones out of "free" map:
                # - sectors 0..39 are reserved (PMBR/GPT headers/table + boot gap policy)
                # - last 33 sectors are reserved for backup GPT metadata
                $usable_start = 40;
                $usable_end = $total_sectors - 34;
            }
            my @segments;
            if (@parts) {
                @parts = sort {
                    (($a->{start} // 0) <=> ($b->{start} // 0))
                    ||
                    (($a->{index} // 0) <=> ($b->{index} // 0))
                } @parts;
                my $cursor = $usable_start;
                for my $p (@parts) {
                    my $ps = $p->{start};
                    my $pe = $p->{end};
                    if (defined($ps) && $ps =~ /^\d+$/ && $ps > $cursor && $cursor <= $usable_end) {
                        my $gap_end = $ps - 1;
                        $gap_end = $usable_end if $gap_end > $usable_end;
                        my $fsize = $ps - $cursor;
                        if ($gap_end >= $cursor) {
                            $fsize = $gap_end - $cursor + 1;
                            push @segments, {
                                type       => 'free',
                                scheme     => $scheme,
                                start      => $cursor,
                                end        => $gap_end,
                                size       => $fsize,
                                size_bytes => $fsize * $sector_size,
                            };
                        }
                    }
                    push @segments, $p;
                    if (defined($pe) && $pe =~ /^\d+$/) {
                        $cursor = $pe + 1 if ($pe + 1) > $cursor;
                    }
                }
                if ($cursor <= $usable_end) {
                    my $fsize = $usable_end - $cursor + 1;
                    push @segments, {
                        type       => 'free',
                        scheme     => $scheme,
                        start      => $cursor,
                        end        => $usable_end,
                        size       => $fsize,
                        size_bytes => $fsize * $sector_size,
                    };
                }
            } elsif ($total_sectors > 0) {
                if ($usable_end >= $usable_start) {
                    my $fsize = $usable_end - $usable_start + 1;
                    push @segments, {
                        type       => 'free',
                        scheme     => $scheme,
                        start      => $usable_start,
                        end        => $usable_end,
                        size       => $fsize,
                        size_bytes => $fsize * $sector_size,
                    };
                } else {
                    push @segments, {
                        type       => 'unpartitioned',
                        scheme     => $scheme,
                        start      => 0,
                        end        => $total_sectors - 1,
                        size       => $total_sectors,
                        size_bytes => $total_sectors * $sector_size,
                    };
                }
            }
            if ($total_sectors > 0) {
                for my $s (@segments) {
                    my $ssz = (defined $s->{size} && $s->{size} =~ /^\d+$/) ? int($s->{size}) : 0;
                    my $pct = ($ssz > 0) ? (100 * $ssz / $total_sectors) : 0;
                    $pct = 0.1 if $pct > 0 && $pct < 0.1;
                    $pct = 100 if $pct > 100;
                    $s->{pct} = sprintf('%.3f', $pct);
                }
            }
            $pmap = {
                scheme      => $scheme,
                sector_size => $sector_size,
                by_index    => \%by_index,
                segments    => \@segments,
            };
        }
        $pmap = {} if ref($pmap) ne 'HASH';
        return $pmap;
    };

    my $pmap = $normalize_pmap->(disk_partition_map($disk_name));
    my $segments = $pmap->{segments} || [];
    my $seg_idx = (defined $in{'seg'} && $in{'seg'} =~ /^\d+$/) ? int($in{'seg'}) : -1;
    my $seg = ($seg_idx >= 0 && $seg_idx < @$segments) ? $segments->[$seg_idx] : undef;
    if (!$advanced_enabled) {
        print &ui_alert(L("MSG_ADVANCED_REQUIRED_QUERY_ONCE"), "info");
    }

    my $pmap_dirty = 0;
    my $scheme_backup_out = '';
    if ($in{'seg_init_scheme'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_scheme'}) {
            print &ui_print_error(L("ERR_CONFIRM_SCHEME_REQUIRED"));
        } else {
            my $scheme = $in{'new_scheme'} || 'gpt';
            my $init_boot = $in{'init_create_boot_part'} ? 1 : 0;
            if ($scheme !~ /^(gpt|mbr)$/) {
                print &ui_print_error(L("ERR_SCHEME_INVALID", $scheme));
            } else {
                eval {
                    must_run($zfsguru_lib::GPART, 'create', '-s', $scheme, $disk_name);
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SCHEME_CREATE_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_SCHEME_CREATED", $disk_name));
                    $pmap_dirty = 1;

                    if ($scheme eq 'gpt' && $init_boot) {
                        my $idx = 0;
                        my $src = L("VALUE_SHIPPED");
                        eval {
                            my ($out, $err) = must_run($zfsguru_lib::GPART, 'add',
                                '-b', '64',
                                '-s', '512K',
                                '-t', 'freebsd-boot',
                                $disk_name
                            );
                            if (defined $out && $out =~ /\b\Q$disk_name\Ep(\d+)\b/) {
                                $idx = int($1);
                            }
                            if (!$idx) {
                                my $plist = gpart_list_partitions_info($disk_name);
                                my $by_index = {};
                                if (ref($plist) eq 'HASH') {
                                    $by_index = $plist->{by_index} || {};
                                } elsif (ref($plist) eq 'ARRAY') {
                                    for my $pp (@$plist) {
                                        next unless ref($pp) eq 'HASH';
                                        next unless defined $pp->{index} && $pp->{index} =~ /^\d+$/;
                                        $by_index->{ int($pp->{index}) } = $pp;
                                    }
                                }
                                for my $i (sort { $a <=> $b } keys %$by_index) {
                                    my $p = $by_index->{$i} || {};
                                    next unless defined $p->{type} && $p->{type} eq 'freebsd-boot';
                                    $idx = int($i);
                                    last;
                                }
                            }
                            die "Could not determine boot partition index" unless $idx;

                            my $paths = bootcode_paths();
                            my $use_system = (-r $paths->{system_pmbr} && -r $paths->{system_gptzfsboot}) ? 1 : 0;
                            my $pmbr = $use_system ? $paths->{system_pmbr} : $paths->{pmbr};
                            my $bootcode = $use_system ? $paths->{system_gptzfsboot} : $paths->{gptzfsboot};
                            die L("ERR_BOOTCODE_FILES_MISSING", $pmbr || '-', $bootcode || '-')
                                if !defined $pmbr || !-r $pmbr || !defined $bootcode || !-r $bootcode;
                            $src = $use_system ? L("VALUE_SYSTEM") : L("VALUE_SHIPPED");
                            must_run($zfsguru_lib::GPART, 'bootcode',
                                '-b', $pmbr,
                                '-p', $bootcode,
                                '-i', $idx,
                                $disk_name
                            );
                        };
                        if ($@) {
                            print &ui_print_error(L("ERR_INIT_BOOT_PART_FAILED", $@));
                        } else {
                            print &ui_print_success(L("SUCCESS_BOOT_PARTITION_CREATED", $disk_name, $idx));
                            print &ui_print_success(L("SUCCESS_BOOTCODE_UPDATED", $disk_name, $idx, $src));
                            $pmap_dirty = 1;
                        }
                    }
                }
            }
        }
    }

    if ($in{'seg_destroy_scheme'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_scheme_destroy'}) {
            print &ui_print_error(L("ERR_CONFIRM_SCHEME_DESTROY_REQUIRED"));
        } else {
            eval { must_run($zfsguru_lib::GPART, 'destroy', '-F', $disk_name); };
            if ($@) {
                print &ui_print_error(L("ERR_SCHEME_DESTROY_FAILED", $@));
            } else {
                print &ui_print_success(L("SUCCESS_SCHEME_DESTROYED", $disk_name));
                $pmap_dirty = 1;
            }
        }
    }

    if ($in{'seg_recover_scheme'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_scheme_recover'}) {
            print &ui_print_error(L("ERR_CONFIRM_SCHEME_RECOVER_REQUIRED"));
        } else {
            my $scheme = $pmap->{scheme} || 'UNKNOWN';
            if ($scheme ne 'GPT') {
                print &ui_print_error(L("ERR_SCHEME_RECOVER_ONLY_GPT", $scheme));
            } else {
                eval { must_run($zfsguru_lib::GPART, 'recover', $disk_name); };
                if ($@) {
                    print &ui_print_error(L("ERR_SCHEME_RECOVER_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_SCHEME_RECOVERED", $disk_name));
                    $pmap_dirty = 1;
                }
            }
        }
    }

    if ($in{'seg_geom_create'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_geom'}) {
            print &ui_print_error(L("ERR_CONFIRM_GEOM_REQUIRED"));
        } else {
            my $label = $in{'geom_label'} || '';
            if (!is_label_name($label)) {
                print &ui_print_error(L("ERR_GEOM_LABEL_INVALID", $label));
            } else {
                eval { glabel_create($label, $disk_name); };
                if ($@) {
                    print &ui_print_error(L("ERR_GEOM_LABEL_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_GEOM_LABEL_CREATED", $label));
                    $pmap_dirty = 1;
                }
            }
        }
    }

    if ($in{'seg_geom_destroy'} && $seg && $seg->{type} eq 'geom') {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_geom'}) {
            print &ui_print_error(L("ERR_CONFIRM_GEOM_REQUIRED"));
        } else {
            my $label = $seg->{label} || '';
            eval { glabel_destroy($label, $disk_name); };
            if ($@) {
                print &ui_print_error(L("ERR_GEOM_LABEL_FAILED", $@));
            } else {
                print &ui_print_success(L("SUCCESS_GEOM_LABEL_DESTROYED", $label));
                $pmap_dirty = 1;
            }
        }
    }

    if ($in{'seg_geom_rename'} && $seg && $seg->{type} eq 'geom') {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_geom'}) {
            print &ui_print_error(L("ERR_CONFIRM_GEOM_REQUIRED"));
        } else {
            my $old = $seg->{label} || '';
            my $new = $in{'geom_label_new'} || '';
            $new =~ s/^\s+|\s+$//g;
            if (!length $old) {
                print &ui_print_error(L("ERR_GEOM_LABEL_FAILED", "Missing current label"));
            } elsif (!is_label_name($new)) {
                print &ui_print_error(L("ERR_GEOM_LABEL_INVALID", $new));
            } elsif ($new eq $old) {
                print &ui_print_error(L("ERR_GEOM_LABEL_NO_CHANGES"));
            } else {
                my $labels = glabel_list();
                my $exists = 0;
                for my $l (@$labels) {
                    next unless defined $l->{label};
                    if ($l->{label} eq $new) {
                        $exists = 1;
                        last;
                    }
                }
                if ($exists) {
                    print &ui_print_error(L("ERR_GEOM_LABEL_EXISTS", $new));
                } else {
                    eval {
                        glabel_destroy($old, $disk_name);
                        glabel_create($new, $disk_name);
                    };
                    if ($@) {
                        print &ui_print_error(L("ERR_GEOM_LABEL_FAILED", $@));
                    } else {
                        print &ui_print_success(L("SUCCESS_GEOM_LABEL_RENAMED", $old, $new));
                        $pmap_dirty = 1;
                    }
                }
            }
        }
    }

    if ($in{'seg_create_partition'} && $seg && $seg->{type} eq 'free') {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_part'}) {
            print &ui_print_error(L("ERR_CONFIRM_PART_REQUIRED"));
        } else {
            my $scheme = $pmap->{scheme} || 'UNKNOWN';
            my @types = $scheme eq 'GPT'
                ? qw(freebsd-zfs freebsd-swap freebsd-boot efi freebsd-ufs freebsd)
                : qw(freebsd fat32);
            my %valid = map { $_ => 1 } @types;
            my $ptype = $in{'part_type'} || '';
            my $trim = $in{'part_trim'} ? 1 : 0;
            my $loc = $in{'part_location'} || 'start';
            $loc =~ s/^\s+|\s+$//g;
            if ($trim && !command_exists($zfsguru_lib::BLKDISCARD)) {
                print &ui_print_error(L("ERR_PART_TRIM_UNAVAILABLE"));
            } elsif (!$valid{$ptype}) {
                print &ui_print_error(L("ERR_PART_TYPE_INVALID", $ptype));
            } elsif ($loc ne 'start' && $loc ne 'end') {
                print &ui_print_error(L("ERR_PART_LOCATION_INVALID", $loc));
            } else {
                my $label = $in{'part_label'} || '';
                my $create_boot = ($scheme eq 'GPT' && $in{'part_create_boot'}) ? 1 : 0;
                if ($label && !is_label_name($label)) {
                    print &ui_print_error(L("ERR_PART_LABEL_INVALID", $label));
                } else {
                    my $size = $in{'part_size'} || '';
                    if ($size && !is_gpart_size($size)) {
                        print &ui_print_error(L("ERR_PART_SIZE_INVALID"));
                    } else {
                        my $align = $in{'part_align'} || '4K';
                        my $sector_size = ($pmap->{sector_size} && $pmap->{sector_size} =~ /^\d+$/) ? int($pmap->{sector_size}) : 512;
                        my $start_sector = (defined $seg->{start} && $seg->{start} =~ /^\d+$/) ? int($seg->{start}) : undef;
                        my $end_sector = (defined $seg->{end} && $seg->{end} =~ /^\d+$/) ? int($seg->{end}) : undef;
                        my $gpt_min_start = ($scheme eq 'GPT' && $ptype ne 'freebsd-boot') ? 2048 : (($scheme eq 'GPT') ? 40 : 0);
                        my $align_sectors = 1;
                        if ($align eq '4K') {
                            $align_sectors = int((4096 + $sector_size - 1) / $sector_size);
                        } elsif ($align eq '1M') {
                            $align_sectors = int((1024 * 1024 + $sector_size - 1) / $sector_size);
                        }
                        $align_sectors = 1 if !$align_sectors || $align_sectors < 1;

                        my $can_create = 1;
                        my $skip_data_create = 0;
                        if ($can_create && $scheme eq 'GPT' && $create_boot
                            && $ptype ne 'freebsd-boot'
                            && defined($start_sector) && defined($end_sector)
                            && $end_sector < 2048) {
                            $skip_data_create = 1;
                        }
                        my $req = undef;
                        if ($size ne '') {
                            $req = gpart_size_to_sectors($size, $sector_size);
                            if (!defined $req || $req <= 0) {
                                print &ui_print_error(L("ERR_PART_SIZE_INVALID"));
                                $can_create = 0;
                            }
                        }
                        if ($can_create && !$skip_data_create && defined($start_sector) && defined($end_sector)) {
                            if ($loc eq 'start') {
                                my $aligned_start = $start_sector;
                                if ($aligned_start < $gpt_min_start) {
                                    $aligned_start = $gpt_min_start;
                                }
                                if ($align_sectors > 1) {
                                    $aligned_start = int(($start_sector + $align_sectors - 1) / $align_sectors) * $align_sectors;
                                    if ($aligned_start < $gpt_min_start) {
                                        $aligned_start = int(($gpt_min_start + $align_sectors - 1) / $align_sectors) * $align_sectors;
                                    }
                                }
                                my $max_fit = $end_sector - $aligned_start + 1;
                                if ($max_fit <= 0) {
                                    print &ui_print_error(L("ERR_PART_SIZE_TOO_LARGE"));
                                    $can_create = 0;
                                } else {
                                    if (!defined($req) || $req <= 0) {
                                        $req = $max_fit;
                                    } elsif ($req > $max_fit) {
                                        print &ui_print_error(L("ERR_PART_SIZE_TOO_LARGE"));
                                        $can_create = 0;
                                    }
                                    $start_sector = $aligned_start if $can_create;
                                }
                            } elsif ($loc eq 'end') {
                                if (!defined($req) || $req <= 0) {
                                    $req = $end_sector - $start_sector + 1;
                                }
                                my $base_start = $end_sector - $req + 1;
                                if ($base_start < $gpt_min_start) {
                                    $base_start = $gpt_min_start;
                                }
                                my $aligned_start = $base_start;
                                if ($align_sectors > 1) {
                                    $aligned_start = int($base_start / $align_sectors) * $align_sectors;
                                }
                                if ($aligned_start < $start_sector || $aligned_start < $gpt_min_start) {
                                    print &ui_print_error(L("ERR_PART_LOCATION_END_TOO_LARGE"));
                                    $can_create = 0;
                                } else {
                                    my $max_fit = $end_sector - $aligned_start + 1;
                                    if ($req > $max_fit) {
                                        print &ui_print_error(L("ERR_PART_LOCATION_END_TOO_LARGE"));
                                        $can_create = 0;
                                    } else {
                                        $start_sector = $aligned_start;
                                    }
                                }
                            }
                        } elsif ($can_create && !$skip_data_create && defined($seg->{size}) && $seg->{size} =~ /^\d+$/ && defined($req) && $req > int($seg->{size})) {
                            print &ui_print_error(L("ERR_PART_SIZE_TOO_LARGE"));
                            $can_create = 0;
                        }
                        if ($can_create && !$skip_data_create && defined($req) && $req > 0) {
                            $size = int($req);
                        }
                        if ($can_create && $create_boot) {
                            my $has_boot = 0;
                            my $boot_slot_busy = 0;
                            for my $s (@$segments) {
                                next unless ref($s) eq 'HASH' && ($s->{type} || '') eq 'partition';
                                my $ps = (defined $s->{start} && $s->{start} =~ /^\d+$/) ? int($s->{start}) : undef;
                                my $pe = (defined $s->{end} && $s->{end} =~ /^\d+$/) ? int($s->{end}) : undef;
                                if (($s->{ptype} || '') eq 'freebsd-boot') {
                                    $has_boot = 1;
                                }
                                if (defined($ps) && defined($pe) && $ps <= 2047 && $pe >= 40 && ($s->{ptype} || '') ne 'freebsd-boot') {
                                    $boot_slot_busy = 1;
                                }
                            }
                            if ($has_boot) {
                                print &ui_print_error(L("ERR_PART_BOOT_EXISTS"));
                                $can_create = 0;
                            } elsif ($boot_slot_busy) {
                                print &ui_print_error(L("ERR_PART_BOOT_SLOT_BUSY"));
                                $can_create = 0;
                            } else {
                                eval { must_run($zfsguru_lib::GPART, 'add', '-t', 'freebsd-boot', '-b', 40, '-s', 2008, $disk_name); };
                                if ($@) {
                                    print &ui_print_error(L("ERR_PART_BOOT_CREATE_FAILED", $@));
                                    $can_create = 0;
                                } else {
                                    $pmap_dirty = 1;
                                }
                            }
                        }
                        if ($can_create && $skip_data_create) {
                            print &ui_print_success(L("SUCCESS_PART_BOOT_CREATED_ONLY", $disk_name));
                            print &ui_alert(L("INFO_PART_SELECT_DATA_SEGMENT_AFTER_BOOT"), "info");
                            $can_create = 0;
                            $pmap_dirty = 1;
                        }

                        my @cmd = ($zfsguru_lib::GPART, 'add', '-t', $ptype);
                        if (defined $start_sector) {
                            push @cmd, '-b', $start_sector;
                        }
                        push @cmd, '-l', $label if ($label && $scheme eq 'GPT');
                        push @cmd, '-s', $size if $size;
                        push @cmd, $disk_name;
                        my ($out, $err) = ('', '');
                        if ($can_create && !$skip_data_create) {
                            eval { ($out, $err) = must_run(@cmd); };
                            if ($@) {
                                print &ui_print_error(L("ERR_PARTITION_CREATE_FAILED", $@));
                            } else {
                                print &ui_print_success(L("SUCCESS_PARTITION_CREATED", $disk_name));
                                if ($trim) {
                                    my $new = '';
                                    if (defined $out && $out =~ /\b([A-Za-z0-9:_\-\.]+[ps]\d+)\b/) {
                                        $new = $1;
                                    }
                                    if (!$new) {
                                        print &ui_alert(L("WARN_PART_TRIM_DEV_UNKNOWN"), "warning");
                                    } else {
                                        my $path = "/dev/$new";
                                        eval {
                                            my ($ok, $e) = disk_blkdiscard($path);
                                            die $e unless $ok;
                                            print &ui_print_success(L("SUCCESS_WIPE_DISCARD", $path));
                                        };
                                        if ($@) {
                                            print &ui_print_error(L("ERR_PART_TRIM_FAILED", $@));
                                        }
                                    }
                                }
                                $pmap_dirty = 1;
                            }
                        }
                    }
                }
            }
        }
    }

    if ($in{'seg_rename_partition_label'} && $seg && $seg->{type} eq 'partition') {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } else {
            my $scheme = $seg->{scheme} || $pmap->{scheme} || 'UNKNOWN';
            my $dev = $seg->{dev} || '';
            my $in_use = '';
            if ($dev) {
                my $mnt = device_mountpoints($dev);
                $in_use = L("MSG_DEVICE_MOUNTED", join(', ', @$mnt)) if @$mnt;
                my $pools = device_in_zpool($dev) || [];
                if (@$pools) {
                    $in_use = ($in_use ? "$in_use; " : '') . L("MSG_DEVICE_IN_POOL", join(', ', @$pools));
                }
            }

            my $cur_label = normalize_label_value($seg->{gpt_label});
            my $new_label = $in{'part_label_rename'};
            $new_label = $in{'part_label'} if !defined($new_label) || $new_label eq '';
            $new_label //= '';

            if ($scheme ne 'GPT') {
                print &ui_print_error(L("ERR_PART_LABEL_RENAME_GPT_ONLY"));
            } elsif (!$new_label) {
                print &ui_print_error(L("ERR_PART_LABEL_EMPTY"));
            } elsif (!is_label_name($new_label)) {
                print &ui_print_error(L("ERR_PART_LABEL_INVALID", $new_label));
            } elsif ($new_label eq $cur_label) {
                print &ui_print_error(L("ERR_PART_LABEL_NO_CHANGES"));
            } elsif (!$in{'confirm_part_label'}) {
                print &ui_print_error(L("ERR_CONFIRM_PART_LABEL_REQUIRED"));
            } elsif ($in_use) {
                print &ui_print_error(L("ERR_DEVICE_IN_USE", $in_use));
            } else {
                eval {
                    must_run($zfsguru_lib::GPART, 'modify', '-i', $seg->{index}, '-l', $new_label, $disk_name);
                };
                if ($@) {
                    print &ui_print_error(L("ERR_PART_LABEL_RENAME_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_PART_LABEL_RENAMED", $dev || $disk_name, $new_label));
                    $pmap_dirty = 1;
                }
            }
        }
    }

    if ($in{'seg_update_partition'} && $seg && $seg->{type} eq 'partition') {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } else {
            my $dev = $seg->{dev} || '';
            my $in_use = '';
            if ($dev) {
                my $mnt = device_mountpoints($dev);
                $in_use = L("MSG_DEVICE_MOUNTED", join(', ', @$mnt)) if @$mnt;
                my $pools = device_in_zpool($dev) || [];
                if (@$pools) {
                    $in_use = ($in_use ? "$in_use; " : '') . L("MSG_DEVICE_IN_POOL", join(', ', @$pools));
                }
            }

            my $scheme = $seg->{scheme} || $pmap->{scheme} || 'UNKNOWN';
            my $cur_ptype = $seg->{ptype} || '';
            my $new_ptype = $in{'part_type'} || '';
            my $cur_label = $seg->{gpt_label} || '';
            my $label = $in{'part_label'} || '';
            my $op = $in{'part_operation'} || 'none';
            my $resize = $in{'part_resize'} || '';

            my @types = $scheme eq 'GPT'
                ? qw(freebsd-zfs freebsd-swap freebsd-boot efi freebsd-ufs freebsd)
                : qw(freebsd fat32);
            my %valid = map { $_ => 1 } @types;
            if ($cur_ptype && !$valid{$cur_ptype} && $cur_ptype =~ /^[A-Za-z0-9][A-Za-z0-9_\-\.]*$/) {
                push @types, $cur_ptype;
                $valid{$cur_ptype} = 1;
            }
            if ($new_ptype && !$valid{$new_ptype}) {
                print &ui_print_error(L("ERR_PART_TYPE_INVALID", $new_ptype));
            } elsif ($label && !is_label_name($label)) {
                print &ui_print_error(L("ERR_PART_LABEL_INVALID", $label));
            } elsif (($op eq 'trimerase') && !command_exists($zfsguru_lib::BLKDISCARD)) {
                print &ui_print_error(L("ERR_PART_TRIM_UNAVAILABLE"));
            } elsif ($op eq 'resize' && !$resize) {
                print &ui_print_error(L("ERR_PART_SIZE_INVALID"));
            } elsif ($op eq 'resize' && !is_gpart_size($resize)) {
                print &ui_print_error(L("ERR_PART_SIZE_INVALID"));
            } else {
                my $is_wipe_op = ($op eq 'zerowrite' || $op eq 'randomwrite' || $op eq 'trimerase') ? 1 : 0;
                my $change_type = ($new_ptype && $new_ptype ne $cur_ptype) ? 1 : 0;
                my $change_label = ($scheme eq 'GPT' && length($label) && $label ne $cur_label) ? 1 : 0;
                my $change_op = ($op && $op ne 'none') ? 1 : 0;
                my $want_change = $change_type || $change_label || $change_op;

                if (!$want_change) {
                    print &ui_print_error(L("ERR_PARTITION_NO_CHANGES"));
                } elsif (!$in{'confirm_part'}) {
                    print &ui_print_error(L("ERR_CONFIRM_PART_REQUIRED"));
                } elsif ($is_wipe_op && !$in{'confirm_part_wipe'}) {
                    print &ui_print_error(L("ERR_CONFIRM_PART_WIPE_REQUIRED"));
                    print &ui_alert(L("MSG_PART_WIPE_WARNING"), "warning");
                } elsif ($in_use) {
                    print &ui_print_error(L("ERR_DEVICE_IN_USE", $in_use));
                } else {
                    my ($started_job, $job_id, $job_log) = (0, '', '');
                    eval {
                        if ($change_type) {
                            must_run($zfsguru_lib::GPART, 'modify', '-i', $seg->{index}, '-t', $new_ptype, $disk_name);
                        }
                        if ($change_label) {
                            must_run($zfsguru_lib::GPART, 'modify', '-i', $seg->{index}, '-l', $label, $disk_name);
                        }
                        if ($change_op) {
                            if ($op eq 'resize') {
                                my $sector_size = ($pmap->{sector_size} && $pmap->{sector_size} =~ /^\d+$/) ? int($pmap->{sector_size}) : 512;
                                my $req = gpart_size_to_sectors($resize, $sector_size);
                                if (!defined($req) || $req <= 0) {
                                    die L("ERR_PART_SIZE_INVALID");
                                }
                                my $max = (defined($seg->{size}) && $seg->{size} =~ /^\d+$/) ? int($seg->{size}) : 0;
                                if ($seg_idx >= 0 && $seg_idx < $#$segments) {
                                    my $n = $segments->[$seg_idx + 1];
                                    if ($n && ($n->{type}||'') =~ /^(free|unpartitioned)$/ && defined($n->{size}) && $n->{size} =~ /^\d+$/) {
                                        $max += int($n->{size});
                                    }
                                }
                                if ($max > 0 && $req > $max) {
                                    die L("ERR_PART_RESIZE_TOO_LARGE");
                                }
                                must_run($zfsguru_lib::GPART, 'resize', '-i', $seg->{index}, '-s', $resize, $disk_name);
                            } elsif ($op eq 'destroy') {
                                must_run($zfsguru_lib::GPART, 'delete', '-i', $seg->{index}, $disk_name);
                            } elsif ($op eq 'zerowrite') {
                                if ($in{'part_wipe_background'}) {
                                    my ($ok, $jid, $log, $err) = start_wipe_job(mode => 'zero', device => $dev);
                                    die $err unless $ok;
                                    ($started_job, $job_id, $job_log) = (1, $jid, $log);
                                } else {
                                    my ($ok, $err) = disk_zero_write($dev);
                                    die $err unless $ok;
                                }
                            } elsif ($op eq 'randomwrite') {
                                if ($in{'part_wipe_background'}) {
                                    my ($ok, $jid, $log, $err) = start_wipe_job(mode => 'random', device => $dev);
                                    die $err unless $ok;
                                    ($started_job, $job_id, $job_log) = (1, $jid, $log);
                                } else {
                                    my ($ok, $err) = disk_random_write($dev);
                                    die $err unless $ok;
                                }
                            } elsif ($op eq 'trimerase') {
                                if ($in{'part_wipe_background'}) {
                                    my ($ok, $jid, $log, $err) = start_wipe_job(mode => 'discard', device => $dev);
                                    die $err unless $ok;
                                    ($started_job, $job_id, $job_log) = (1, $jid, $log);
                                } else {
                                    my ($ok, $err) = disk_blkdiscard($dev);
                                    die $err unless $ok;
                                }
                            } else {
                                die L("ERR_PART_OPERATION_REQUIRED");
                            }
                        }
                    };
                    if ($@) {
                        print &ui_print_error(L("ERR_PARTITION_UPDATE_FAILED", $@));
                    } else {
                        if ($started_job) {
                            print &ui_print_success(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $job_log));
                            my $job_file = $job_log || "wipe_$job_id.log";
                            my $view_link = "disks.cgi?action=job_log&job=" . &url_encode($job_file) . "&disk=" . &url_encode($disk_name);
                            print "<p><a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" .
                                  &html_escape($view_link) . "'>" . &html_escape(L("BTN_VIEW_LOG")) . "</a></p>";
                        } else {
                            print &ui_print_success(L("SUCCESS_PARTITION_UPDATED", $dev || $disk_name));
                        }
                        $pmap_dirty = 1 if ($change_type || $change_label || $op eq 'resize' || $op eq 'destroy');
                    }
                }
            }
        }
    }

    my $is_gpt_boot_seg = ($seg
        && $seg->{type} eq 'partition'
        && (($seg->{scheme} || $pmap->{scheme} || '') eq 'GPT')
        && (($seg->{ptype} || '') eq 'freebsd-boot')) ? 1 : 0;

    if (($in{'seg_update_bootcode'} || $in{'seg_update_bootcode_system'} || $in{'seg_destroy_boot_partition'})
        && !$is_gpt_boot_seg) {
        print &ui_print_error(L("ERR_BOOTCODE_SEGMENT_REQUIRED"));
    }

    if ($is_gpt_boot_seg && ($in{'seg_update_bootcode'} || $in{'seg_update_bootcode_system'})) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_bootcode_update'}) {
            print &ui_print_error(L("ERR_CONFIRM_BOOTCODE_UPDATE_REQUIRED"));
        } else {
            my $paths = bootcode_paths();
            my $use_system = $in{'seg_update_bootcode_system'} ? 1 : 0;
            my $pmbr = $use_system ? $paths->{system_pmbr} : $paths->{pmbr};
            my $kind = $in{'bootcode_kind'} || 'zfs';
            $kind = 'zfs' if $kind ne 'ufs' && $kind ne 'zfs';
            my $boot_key = ($kind eq 'ufs') ? 'gptboot' : 'gptzfsboot';
            my $bootcode = $use_system ? $paths->{"system_$boot_key"} : $paths->{$boot_key};
            my $src = $use_system ? L("VALUE_SYSTEM") : L("VALUE_SHIPPED");
            if (!defined $pmbr || !-r $pmbr || !defined $bootcode || !-r $bootcode) {
                print &ui_print_error(L("ERR_BOOTCODE_FILES_MISSING", $pmbr || '-', $bootcode || '-'));
            } else {
                my $idx = $seg->{index};
                eval {
                    must_run($zfsguru_lib::GPART, 'bootcode',
                        '-b', $pmbr,
                        '-p', $bootcode,
                        '-i', $idx,
                        $disk_name
                    );
                };
                if ($@) {
                    print &ui_print_error(L("ERR_BOOTCODE_UPDATE_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_BOOTCODE_UPDATED", $disk_name, $idx, $src));
                }
            }
        }
    }

    if ($is_gpt_boot_seg && $in{'seg_destroy_boot_partition'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_bootcode_destroy'}) {
            print &ui_print_error(L("ERR_CONFIRM_BOOTCODE_DESTROY_REQUIRED"));
        } else {
            my $dev = $seg->{dev} || '';
            my $in_use = '';
            if ($dev) {
                my $mnt = device_mountpoints($dev);
                $in_use = L("MSG_DEVICE_MOUNTED", join(', ', @$mnt)) if @$mnt;
                my $pools = device_in_zpool($dev) || [];
                if (@$pools) {
                    $in_use = ($in_use ? "$in_use; " : '') . L("MSG_DEVICE_IN_POOL", join(', ', @$pools));
                }
            }
            if ($in_use) {
                print &ui_print_error(L("ERR_DEVICE_IN_USE", $in_use));
            } else {
                my $idx = $seg->{index};
                eval { must_run($zfsguru_lib::GPART, 'delete', '-i', $idx, $disk_name); };
                if ($@) {
                    print &ui_print_error(L("ERR_BOOT_PARTITION_DESTROY_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_BOOT_PARTITION_DESTROYED", $disk_name, $idx));
                    $pmap_dirty = 1;
                }
            }
        }
    }

    my $is_mbr_part_seg = ($seg
        && $seg->{type} eq 'partition'
        && (($seg->{scheme} || $pmap->{scheme} || '') eq 'MBR')) ? 1 : 0;

    if ($in{'seg_set_mbr_active'} && !$is_mbr_part_seg) {
        print &ui_print_error(L("ERR_MBR_ACTIVE_ONLY"));
    }

    if ($is_mbr_part_seg && $in{'seg_set_mbr_active'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_mbr_active'}) {
            print &ui_print_error(L("ERR_CONFIRM_MBR_ACTIVE_REQUIRED"));
        } else {
            my $idx = $seg->{index};
            eval { must_run($zfsguru_lib::GPART, 'set', '-a', 'active', '-i', $idx, $disk_name); };
            if ($@) {
                print &ui_print_error(L("ERR_MBR_ACTIVE_SET_FAILED", $@));
            } else {
                print &ui_print_success(L("SUCCESS_MBR_ACTIVE_SET", $disk_name, $idx));
                $pmap_dirty = 1;
            }
        }
    }

    if ($in{'seg_unset_mbr_active'} && !$is_mbr_part_seg) {
        print &ui_print_error(L("ERR_MBR_ACTIVE_ONLY"));
    }

    if ($is_mbr_part_seg && $in{'seg_unset_mbr_active'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_mbr_active'}) {
            print &ui_print_error(L("ERR_CONFIRM_MBR_ACTIVE_REQUIRED"));
        } elsif (!gpart_supports_subcommand('unset')) {
            print &ui_print_error(L("ERR_GPART_UNSET_UNSUPPORTED"));
        } else {
            my $idx = $seg->{index};
            eval { must_run($zfsguru_lib::GPART, 'unset', '-a', 'active', '-i', $idx, $disk_name); };
            if ($@) {
                print &ui_print_error(L("ERR_MBR_ACTIVE_UNSET_FAILED", $@));
            } else {
                print &ui_print_success(L("SUCCESS_MBR_ACTIVE_UNSET", $disk_name, $idx));
                $pmap_dirty = 1;
            }
        }
    }

    if ($in{'scheme_backup'}) {
        my ($rc, $out, $err) = run_cmd($zfsguru_lib::GPART, 'backup', $disk_name);
        if ($rc != 0) {
            print &ui_print_error(L("ERR_SCHEME_BACKUP_FAILED", $err || $out || 'backup failed'));
        } else {
            $scheme_backup_out = $out || '';
            print &ui_print_success(L("SUCCESS_SCHEME_BACKED_UP", $disk_name));
        }
    }

    if ($in{'scheme_restore'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
        } elsif (!$in{'confirm_scheme_restore'}) {
            print &ui_print_error(L("ERR_CONFIRM_SCHEME_RESTORE_REQUIRED"));
        } else {
            my $force = $in{'scheme_restore_force'} ? 1 : 0;
            if ($force && !$in{'confirm_scheme_restore_force'}) {
                print &ui_print_error(L("ERR_CONFIRM_SCHEME_RESTORE_FORCE_REQUIRED"));
            } else {
                my $data = $in{'scheme_restore_data'} // '';
                $data =~ s/\r\n/\n/g;
                if ($data !~ /\S/) {
                    print &ui_print_error(L("ERR_SCHEME_RESTORE_DATA_REQUIRED"));
                } else {
                    my ($ok, $out, $err) = (0, '', '');
                    eval { ($ok, $out, $err) = gpart_restore(disk => $disk_name, data => $data, force => $force); };
                    if ($@) {
                        print &ui_print_error(L("ERR_SCHEME_RESTORE_FAILED", $@));
                    } elsif (!$ok) {
                        print &ui_print_error(L("ERR_SCHEME_RESTORE_FAILED", $err || $out || 'restore failed'));
                    } else {
                        print &ui_print_success(L("SUCCESS_SCHEME_RESTORED", $disk_name));
                        $pmap_dirty = 1;
                    }
                }
            }
        }
    }

    if ($pmap_dirty) {
        $pmap = $normalize_pmap->(disk_partition_map($disk_name));
        $segments = $pmap->{segments} || [];
        $seg = ($seg_idx >= 0 && $seg_idx < @$segments) ? $segments->[$seg_idx] : undef;
    }

    if ($in{'kill_bg_job'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
            return;
        }
        my $job = $in{'kill_bg_job'};
        if (!defined($job) || $job !~ /^[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_WIPE_LOG_INVALID"));
        } else {
            my ($ok, $msg) = zfsguru_kill_job(file => $job);
            if ($ok) {
                print &ui_print_success(L("SUCCESS_WIPE_JOB_KILLED", $job));
            } else {
                print &ui_print_error(L("ERR_WIPE_JOB_KILL_FAILED", $msg || 'kill failed'));
            }
        }
    }

    if ($in{'clear_bg_logs'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
            return;
        }
        my ($ok, $err, $count) = zfsguru_clear_job_logs();
        if ($ok) {
            print &ui_print_success(L("SUCCESS_BG_LOGS_CLEARED", $count));
        } else {
            print &ui_print_error(L("ERR_BG_LOGS_CLEAR_FAILED", $err || 'clear failed'));
        }
    }

    if ($in{'wipe_zero'} || $in{'wipe_random'} || $in{'wipe_secure'} || $in{'wipe_ata'} || $in{'wipe_discard'}) {
        if (!$advanced_enabled) {
            print &ui_print_error(L("ERR_ADVANCED_REQUIRED"));
            return;
        }
        my $target = $in{'wipe_target'} || '';
        $target =~ s/^\s+|\s+$//g;
        my $dev = $target;
        if ($dev !~ m{^/dev/}) {
            $dev = "/dev/$dev";
        }
        if ($dev !~ m{^/dev/[A-Za-z0-9._/\-]+$} || !$allowed_target{$dev}) {
            print &ui_print_error(L("ERR_WIPE_TARGET_INVALID", $target));
        } elsif ($in{'wipe_mode'} && $in{'wipe_mode'} eq 'quick' && !$in{'wipe_zero'}) {
            print &ui_print_error(L("ERR_WIPE_QUICK_ONLY_ZERO"));
        } elsif (!$in{'confirm_wipe'}) {
            print &ui_print_error(L("ERR_CONFIRM_WIPE_REQUIRED"));
        } elsif (($in{'wipe_secure'} || $in{'wipe_ata'}) && !$in{'confirm_secure'}) {
            print &ui_print_error(L("ERR_CONFIRM_SECURE_WIPE_REQUIRED"));
        } else {
            my @check = ($dev);
            my $real = eval { realpath($dev) } || '';
            push @check, $real if ($real && $real ne $dev);
            my %seen_check;
            @check = grep { $_ && !$seen_check{$_}++ } @check;

            my %mounts;
            my %pools;
            for my $p (@check) {
                my $mnt = device_mountpoints($p);
                $mounts{$_} = 1 for @$mnt;
                my $pl = device_in_zpool($p) || [];
                $pools{$_} = 1 for @$pl;
            }
            my @mnts = sort keys %mounts;
            my @pls  = sort keys %pools;
            my @use_msgs;
            push @use_msgs, L("MSG_DEVICE_MOUNTED", join(', ', @mnts)) if @mnts;
            push @use_msgs, L("MSG_DEVICE_IN_POOL", join(', ', @pls)) if @pls;
            my $in_use = join('; ', @use_msgs);

            if ($in_use && !$in{'confirm_wipe_in_use'}) {
                print &ui_print_error(L("ERR_WIPE_TARGET_IN_USE", $in_use));
                return;
            }
            if ($in_use) {
                print &ui_alert(L("WARN_WIPE_TARGET_IN_USE", $in_use), "warning");
            }

            my $mode = $in{'wipe_secure'} ? 'secure'
                     : $in{'wipe_random'} ? 'random'
                     : $in{'wipe_ata'} ? 'ata'
                     : $in{'wipe_discard'} ? 'discard'
                     : 'zero';
            if (($mode eq 'secure' || $mode eq 'ata') && $dev ne "/dev/$disk_name") {
                print &ui_print_error(L("ERR_WIPE_SECURE_WHOLE_DISK"));
                return;
            }
            my $quick = ($in{'wipe_mode'} && $in{'wipe_mode'} eq 'quick') ? 1 : 0;
            my $quick_mib = $in{'wipe_mib'} || 16;
            if ($quick && ($quick_mib !~ /^\d+$/ || $quick_mib < 1 || $quick_mib > 1048576)) {
                print &ui_print_error(L("ERR_WIPE_SIZE_INVALID"));
                return;
            }
            if ($in{'wipe_background'}) {
                my ($ok, $job_id, $log, $err) = start_wipe_job(
                    mode => $mode,
                    device => $dev,
                    quick => $quick,
                    quick_mib => $quick_mib,
                );
                if ($ok) {
                    print &ui_print_success(L("SUCCESS_WIPE_JOB_STARTED", $job_id, $log));
                    my $job_file = $log || "wipe_$job_id.log";
                    my $view_link = "disks.cgi?action=job_log&job=" . &url_encode($job_file) . "&disk=" . &url_encode($disk_name);
                    print "<p><a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" .
                          &html_escape($view_link) . "'>" . &html_escape(L("BTN_VIEW_LOG")) . "</a></p>";
                } else {
                    print &ui_print_error(L("ERR_WIPE_JOB_FAILED", $err || 'failed to start job'));
                }
            } else {
                eval {
                    if ($quick) {
                        disk_wipe_head($dev, $quick_mib);
                        print &ui_print_success(L("SUCCESS_WIPE_QUICK", $dev, $quick_mib));
                    } elsif ($mode eq 'zero') {
                        my ($ok, $err) = disk_zero_write($dev);
                        die $err || "zero write failed" unless $ok;
                        print &ui_print_success(L("SUCCESS_WIPE_ZERO", $dev));
                    } elsif ($mode eq 'random') {
                        my ($ok, $err) = disk_random_write($dev);
                        die $err || "random write failed" unless $ok;
                        print &ui_print_success(L("SUCCESS_WIPE_RANDOM", $dev));
                    } elsif ($mode eq 'ata') {
                        my ($ok, $err) = disk_ata_secure_erase($dev);
                        die $err || "ATA secure erase failed" unless $ok;
                        print &ui_print_success(L("SUCCESS_WIPE_ATA", $dev));
                    } elsif ($mode eq 'discard') {
                        my ($ok, $err) = disk_blkdiscard($dev);
                        die $err || "blkdiscard failed" unless $ok;
                        print &ui_print_success(L("SUCCESS_WIPE_DISCARD", $dev));
                    } else {
                        my ($ok, $err) = disk_secure_erase($dev);
                        die $err || "secure erase failed" unless $ok;
                        print &ui_print_success(L("SUCCESS_WIPE_SECURE", $dev));
                    }
                };
                if ($@) {
                    print &ui_print_error(L("ERR_WIPE_FAILED", $@));
                }
            }
        }
    }

    my $info = diskinfo($disk_name);
    if (!$info) {
        print &ui_print_error(L("ERR_DISKINFO_FAILED", $disk_name));
        return;
    }

    my $gpart = gpart_show($disk_name);
    my $scheme_corrupt = ($gpart && $gpart =~ /\bCORRUPT\b/i) ? 1 : 0;

    print &ui_subheading(L("SUB_DISK_QUERY", $disk_name));
    print &ui_table_start(L("TABLE_DISK_QUERY_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_DISK_NAME"), $disk_name);
    print &ui_table_row(L("ROW_MEDIA_SIZE"), &format_bytes($info->{mediasize}));
    print &ui_table_row(L("ROW_SECTOR_SIZE"), $info->{sectorsize} . " " . L("UNIT_BYTES"));
    print &ui_table_row(L("ROW_SECTOR_COUNT"), $info->{sectorcount});
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_DISK_PARTITION_MAP", $disk_name));
    if (@$segments) {
        my $map_html = "";
        $map_html .= "<div class='zfsguru-pmap'>";
        for my $i (0 .. $#$segments) {
            my $s = $segments->[$i];
            my $pct = $s->{pct} || 0;
            my $label = $s->{type};
            if ($s->{type} eq 'free') {
                $label = L("SEG_FREE");
            } elsif ($s->{type} eq 'unpartitioned') {
                $label = L("SEG_UNPARTITIONED");
            } elsif ($s->{type} eq 'geom') {
                $label = L("SEG_GEOM") . ($s->{label} ? ": $s->{label}" : '');
            } elsif ($s->{type} eq 'partition') {
                $label = $s->{ptype} || 'partition';
            }
            my @classes = ('zfsguru-pmap-seg');
            my $t = $s->{type} || '';
            $t =~ s/[^A-Za-z0-9_\-]+/_/g;
            push @classes, "zfsguru-pmap-$t" if length $t;
            push @classes, "zfsguru-pmap-selected" if ($seg_idx == $i);
            my $class = join(' ', @classes);
            my $href = "disks.cgi?action=query&disk=" . &url_encode($disk_name) . "&seg=$i";
            $map_html .= "<a class='" . &html_escape($class) . "' href='" . &html_escape($href) . "' title='" . &html_escape($label) .
                         "' style='width:${pct}%;'>" . &html_escape($label) . "</a>";
        }
        $map_html .= "</div>";
        print $map_html;

        my @pmap_heads = (
            L("COL_SEGMENT"),
            L("COL_START"),
            L("COL_END"),
            L("COL_SIZE"),
            L("COL_PART_LABEL"),
            L("COL_DEVICE"),
            L("COL_ACTIONS"),
        );
        my @pmap_data;
        for my $i (0 .. $#$segments) {
            my $s = $segments->[$i];
            my $seg_label = $s->{type};
            if ($s->{type} eq 'free') {
                $seg_label = L("SEG_FREE");
            } elsif ($s->{type} eq 'unpartitioned') {
                $seg_label = L("SEG_UNPARTITIONED");
            } elsif ($s->{type} eq 'geom') {
                $seg_label = L("SEG_GEOM") . ($s->{label} ? ": $s->{label}" : '');
            } elsif ($s->{type} eq 'partition') {
                my $label = normalize_label_value($s->{gpt_label});
                my $active = ($s->{mbr_active}) ? (' ' . L("LBL_MBR_ACTIVE")) : '';
                $seg_label = ($s->{ptype} || 'partition') . ($s->{name} ? " ($s->{name})" : '') . $active;
            }
            my $size = $s->{size_bytes} ? format_bytes($s->{size_bytes}) : '-';
            my $plabel = '-';
            if ($s->{type} eq 'partition') {
                $plabel = normalize_label_value($s->{gpt_label}) || '-';
            } elsif ($s->{type} eq 'geom') {
                $plabel = $s->{label} || '-';
            }
            my $dev = $s->{dev} || '-';
            my $seg_href = "disks.cgi?action=query&disk=" . &url_encode($disk_name) . "&seg=$i";
            my $seg_class = ($seg_idx == $i) ? 'primary' : 'default';
            my $sel_txt = ($s->{type} && ($s->{type} eq 'free' || $s->{type} eq 'unpartitioned'))
                ? L("BTN_SELECT_ADD_PARTITION")
                : L("BTN_SELECT_SEGMENT");
            my $select = &ui_link_icon($seg_href, $sel_txt, undef, { class => $seg_class });
            push @pmap_data, [
                &html_escape($seg_label),
                &html_escape($s->{start}),
                &html_escape($s->{end}),
                $size,
                &html_escape($plabel),
                &html_escape($dev),
                $select
            ];
        }
        print &ui_columns_table(\@pmap_heads, 100, \@pmap_data, undef, 1,
            undef, L("ERR_PARTITION_MAP_UNAVAILABLE", $disk_name));
    } else {
        print &ui_print_error(L("ERR_PARTITION_MAP_UNAVAILABLE", $disk_name));
    }

    print &ui_hr();
    if ($seg) {
        my $seg_type = $seg->{type} || 'unknown';
        my %seg_type_text = (
            free         => L("VALUE_FREE"),
            unpartitioned=> L("VALUE_UNPARTITIONED"),
            partition    => L("VALUE_PARTITION"),
            geom         => L("VALUE_GEOM_LABEL"),
        );
        my $seg_type_disp = $seg_type_text{$seg_type} || $seg_type;
        my $seg_range = '-';
        if (defined $seg->{start} && defined $seg->{end}) {
            $seg_range = $seg->{start} . " .. " . $seg->{end};
        }
        my $seg_size_disp = '-';
        if (defined $seg->{size_bytes} && $seg->{size_bytes} =~ /^\d+$/) {
            $seg_size_disp = format_bytes(int($seg->{size_bytes}));
            if (defined $seg->{size} && $seg->{size} =~ /^\d+$/) {
                $seg_size_disp .= " (" . $seg->{size} . " " . L("UNIT_SECTORS") . ")";
            }
        } elsif (defined $seg->{size} && $seg->{size} =~ /^\d+$/) {
            $seg_size_disp = $seg->{size} . " " . L("UNIT_SECTORS");
        }

        print &ui_table_start(L("TABLE_SEGMENT_DETAILS"), "width=100%", 2);
        print &ui_table_row(L("ROW_SEGMENT_INDEX"), $seg_idx);
        print &ui_table_row(L("ROW_SEGMENT_TYPE"), &html_escape($seg_type_disp));
        print &ui_table_row(L("ROW_SEGMENT_RANGE"), &html_escape($seg_range));
        print &ui_table_row(L("ROW_SEGMENT_SIZE"), &html_escape($seg_size_disp));
        if ($seg_type eq 'partition') {
            my $ss = ($pmap->{sector_size} && $pmap->{sector_size} =~ /^\d+$/) ? int($pmap->{sector_size}) : 512;
            my ($align_step, $align_label) = detect_partition_alignment($seg, $ss);
            my $seg_label = normalize_label_value($seg->{gpt_label});
            print &ui_table_row(L("ROW_DEVICE"), &html_escape($seg->{dev} || '-'));
            print &ui_table_row(L("ROW_PART_TYPE"), &html_escape($seg->{ptype} || '-'));
            print &ui_table_row(L("ROW_PART_LABEL"), &html_escape($seg_label || '-'));
            print &ui_table_row(L("ROW_PART_ALIGNMENT"), &html_escape($align_label || 'SECT'));
        } elsif ($seg_type eq 'geom') {
            print &ui_table_row(L("ROW_GEOM_LABEL_NAME"), &html_escape($seg->{label} || '-'));
            print &ui_table_row(L("ROW_DEVICE"), &html_escape($seg->{dev} || '-'));
        }
        print &ui_table_end();

        if ($seg->{type} eq 'unpartitioned') {
            print &ui_subheading(L("SUB_INIT_SCHEME"));
            print &ui_form_start("disks.cgi", "post");
            print &ui_hidden("action", "query");
            print &ui_hidden("disk", $disk_name);
            print &ui_table_start(L("TABLE_INIT_SCHEME"), "width=100%", 2);
            print &ui_table_row(L("ROW_PARTITION_SCHEME"),
                &ui_select("new_scheme", "gpt", [
                    [ "gpt", L("OPT_GPT_RECOMMENDED") ],
                    [ "mbr", L("OPT_MBR_LEGACY") ],
                ]));
            print &ui_table_row(L("ROW_INIT_CREATE_BOOT_PART"),
                &ui_checkbox("init_create_boot_part", 1, L("LBL_INIT_CREATE_BOOT_PART"), 0) .
                "<br><small>" . L("HINT_INIT_CREATE_BOOT_PART") . "</small>");
            print &ui_table_row(L("ROW_CONFIRM_SCHEME"),
                &ui_checkbox("confirm_scheme", 1, L("LBL_CONFIRM_SCHEME"), 0));
            print &ui_table_end();
            print &ui_form_end([ [ "seg_init_scheme", L("BTN_CREATE_SCHEME") ] ]);

            print &ui_hr();
            print &ui_subheading(L("SUB_GEOM_LABEL"));
            print &ui_form_start("disks.cgi", "post");
            print &ui_hidden("action", "query");
            print &ui_hidden("disk", $disk_name);
            print &ui_table_start(L("TABLE_GEOM_LABEL"), "width=100%", 2);
            print &ui_table_row(L("ROW_GEOM_LABEL_NAME"), &ui_textbox("geom_label", "", 20));
            print &ui_table_row(L("ROW_CONFIRM_GEOM"),
                &ui_checkbox("confirm_geom", 1, L("LBL_CONFIRM_GEOM"), 0));
            print &ui_table_end();
            print &ui_form_end([ [ "seg_geom_create", L("BTN_CREATE_GEOM_LABEL") ] ]);
        } elsif ($seg->{type} eq 'geom') {
            print &ui_subheading(L("SUB_GEOM_LABEL"));
            print "<p>" . L("MSG_GEOM_LABEL_INFO", $seg->{label} || '-') . "</p>";
            print &ui_form_start("disks.cgi", "post");
            print &ui_hidden("action", "query");
            print &ui_hidden("disk", $disk_name);
            print &ui_hidden("seg", $seg_idx);
            print &ui_table_start(L("TABLE_GEOM_LABEL"), "width=100%", 2);
            print &ui_table_row(L("ROW_GEOM_LABEL_NAME"), &html_escape($seg->{label} || '-'));
            print &ui_table_row(L("ROW_GEOM_LABEL_NEW_NAME"), &ui_textbox("geom_label_new", "", 20));
            print &ui_table_row(L("ROW_CONFIRM_GEOM"),
                &ui_checkbox("confirm_geom", 1, L("LBL_CONFIRM_GEOM"), 0));
            print &ui_table_end();
            print &ui_form_end([
                [ "seg_geom_rename", L("BTN_RENAME_GEOM_LABEL") ],
                [ "seg_geom_destroy", L("BTN_DESTROY_GEOM_LABEL"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ],
            ]);
        } elsif ($seg->{type} eq 'free') {
            my $scheme = $pmap->{scheme} || 'UNKNOWN';
            my @types = $scheme eq 'GPT'
                ? qw(freebsd-zfs freebsd-swap freebsd-boot efi freebsd-ufs freebsd)
                : qw(freebsd fat32);
            my @type_opts = map { [ $_, $_ ] } @types;

            print &ui_subheading(L("SUB_CREATE_PARTITION"));
            print &ui_form_start("disks.cgi", "post");
            print &ui_hidden("action", "query");
            print &ui_hidden("disk", $disk_name);
            print &ui_hidden("seg", $seg_idx);
            print &ui_table_start(L("TABLE_CREATE_PARTITION"), "width=100%", 2);
            print &ui_table_row(L("ROW_PART_TYPE"), &ui_select("part_type", $types[0] || '', \@type_opts));
            if ($scheme eq 'GPT') {
                print &ui_table_row(L("ROW_PART_LABEL"), &ui_textbox("part_label", "", 20));
                my $has_boot = 0;
                for my $s (@$segments) {
                    next unless ref($s) eq 'HASH' && ($s->{type} || '') eq 'partition';
                    if (($s->{ptype} || '') eq 'freebsd-boot') {
                        $has_boot = 1;
                        last;
                    }
                }
                if (!$has_boot) {
                    print &ui_table_row(L("ROW_PART_CREATE_BOOT"),
                        &ui_checkbox("part_create_boot", 1, L("LBL_PART_CREATE_BOOT"), ($in{'part_create_boot'} ? 1 : 0))
                        . "<br><small>" . L("HINT_PART_CREATE_BOOT") . "</small>");
                }
            }
            my $free_hint = '';
            if (defined $seg->{size_bytes} && $seg->{size_bytes} =~ /^\d+$/ && defined $seg->{size} && $seg->{size} =~ /^\d+$/) {
                $free_hint = "<br><small>" . L("HINT_FREE_SEGMENT_SIZE", format_bytes(int($seg->{size_bytes})), int($seg->{size})) . "</small>";
            }
            print &ui_table_row(L("ROW_PART_SIZE"),
                do {
                    my $part_size_ui = &ui_textbox("part_size", ($in{'part_size'} // ''), 12);
                    if ($part_size_ui !~ /\bid=['"]part-size-input['"]/i) {
                        $part_size_ui =~ s/<input\b/<input id='part-size-input'/i;
                    }
                    my $part_size_slider = "";
                    my $part_max_sectors = (defined($seg->{size}) && $seg->{size} =~ /^\d+$/) ? int($seg->{size}) : 0;
                    my $ss = ($pmap->{sector_size} && $pmap->{sector_size} =~ /^\d+$/) ? int($pmap->{sector_size}) : 512;
                    if ($part_max_sectors > 0) {
                        my $default_val = $part_max_sectors;
                        $part_size_slider =
                            "<input type='hidden' id='part-size-max-sectors' value='$part_max_sectors'>"
                          . "<input type='hidden' id='part-size-sector-size' value='$ss'>"
                          . "<div id='part-size-slider-wrap' style='margin-top:6px'>"
                          . "<input type='range' id='part-size-slider' min='1' max='$part_max_sectors' value='$default_val' style='width:320px;vertical-align:middle' "
                          . "oninput=\"(function(s){var v=s.value;var i=document.getElementById('part-size-input');if(i){i.value=v;}var l=document.getElementById('part-size-slider-value');if(l){l.textContent=v+' " . L("UNIT_SECTORS") . "';}})(this)\"> "
                          . "<span id='part-size-slider-value'>" . int($default_val) . " " . L("UNIT_SECTORS") . "</span>"
                          . "<br><small>" . &html_escape(L("HINT_PART_SIZE_SLIDER")) . "</small>"
                          . "</div>";
                    }
                    $part_size_ui . $part_size_slider . " " . L("HINT_PART_SIZE_MAX") . $free_hint
                });
            print &ui_table_row(L("ROW_PART_ALIGN"),
                &ui_select("part_align", ($in{'part_align'} || "4K"), [
                    [ "SECT", L("OPT_ALIGN_SECT") ],
                    [ "4K", L("OPT_ALIGN_4K") ],
                    [ "1M", L("OPT_ALIGN_1M") ],
                ]));
            print &ui_table_row(L("ROW_PART_LOCATION"),
                &ui_select("part_location", "start", [
                    [ "start", L("OPT_PART_LOC_START") ],
                    [ "end", L("OPT_PART_LOC_END") ],
                ]) . "<br><small>" . L("HINT_PART_LOCATION") . "</small>");
            my $blkdiscard_supported = command_exists($zfsguru_lib::BLKDISCARD);
            if ($blkdiscard_supported) {
                print &ui_table_row(L("ROW_PART_TRIM"),
                    &ui_checkbox("part_trim", 1, L("LBL_PART_TRIM"), 0));
            } else {
                print &ui_table_row(L("ROW_PART_TRIM"), L("MSG_PART_TRIM_UNAVAILABLE"));
            }
            print &ui_table_row(L("ROW_CONFIRM_PART"),
                &ui_checkbox("confirm_part", 1, L("LBL_CONFIRM_PART"), 0));
            print &ui_table_end();
            print &ui_form_end([ [ "seg_create_partition", L("BTN_CREATE_PARTITION") ] ]);
            print "<script>
(function(){
  function byName(n){ return document.querySelector('[name=\"'+n+'\"]'); }
  function el(id){ return document.getElementById(id); }
  function parseToSectors(v, ss){
    if(!v) return null;
    v = String(v).trim();
    if(!v) return null;
    if(/^[0-9]+$/.test(v)) return parseInt(v,10);
    var m = v.match(/^([0-9]+(?:\\.[0-9]+)?)([KMGTP])$/i);
    if(!m) return null;
    var n = parseFloat(m[1]);
    var u = m[2].toUpperCase();
    var p = {K:1,M:2,G:3,T:4,P:5}[u] || 0;
    var bytes = n * Math.pow(1024,p);
    return Math.ceil(bytes / ss);
  }
  function humanFromSectors(sec, ss){
    var bytes = sec * ss;
    var gib = bytes / (1024*1024*1024);
    if (gib >= 1) return gib.toFixed(2) + ' GiB';
    var mib = bytes / (1024*1024);
    return mib.toFixed(2) + ' MiB';
  }
  function alignToStep(align, ss){
    var a = String(align || '4K').toUpperCase();
    if(a === 'SECT') return 1;
    if(a === '1M') return Math.max(1, Math.ceil((1024*1024) / ss));
    return Math.max(1, Math.ceil(4096 / ss)); // 4K default
  }
  function snapToStep(v, step, min, max){
    if(step <= 1) return Math.max(min, Math.min(max, v));
    var n = Math.floor(v / step) * step;
    if(n < step) n = step;
    if(n < min) n = min;
    if(n > max) n = max;
    return n;
  }
  var inEl = el('part-size-input') || byName('part_size');
  var slider = el('part-size-slider');
  var label = el('part-size-slider-value');
  var maxEl = el('part-size-max-sectors');
  var ssEl = el('part-size-sector-size');
  var alignEl = byName('part_align');
  if(!inEl || !slider || !label || !maxEl || !ssEl){ return; }
  var ss = parseInt(ssEl.value || '512', 10);
  var currentStep = alignToStep(alignEl ? alignEl.value : '4K', ss);
  function render(sec){
    label.textContent = sec + ' sectors (~' + humanFromSectors(sec, ss) + ')';
  }
  function applyAlignStep(){
    currentStep = alignToStep(alignEl ? alignEl.value : '4K', ss);
    slider.step = String(currentStep);
    if(currentStep > 1){
      slider.min = String(currentStep);
    } else {
      slider.min = '1';
    }
    var min = parseInt(slider.min || '1', 10);
    var max = parseInt(slider.max || maxEl.value || '1', 10);
    var cur = parseInt(slider.value || '1', 10);
    cur = snapToStep(cur, currentStep, min, max);
    slider.value = String(cur);
    inEl.value = String(cur);
    render(cur);
  }
  function fromSlider(){
    var min = parseInt(slider.min || '1', 10);
    var max = parseInt(slider.max || maxEl.value || '1', 10);
    var v = parseInt(slider.value || '1', 10);
    v = snapToStep(v, currentStep, min, max);
    slider.value = String(v);
    inEl.value = String(v);
    render(v);
  }
  function fromInput(){
    var req = parseToSectors(inEl.value, ss);
    if(req === null) return;
    var min = parseInt(slider.min || '1', 10);
    var max = parseInt(slider.max || maxEl.value || '1', 10);
    req = snapToStep(req, currentStep, min, max);
    slider.value = String(req);
    inEl.value = String(req);
    render(req);
  }
  slider.addEventListener('input', fromSlider);
  slider.addEventListener('change', fromSlider);
  inEl.addEventListener('input', fromInput);
  inEl.addEventListener('change', fromInput);
  var form = slider.closest ? slider.closest('form') : null;
  if(form){
    form.addEventListener('submit', function(){
      inEl.value = String(slider.value || inEl.value || '');
    });
  }
  if(alignEl){
    alignEl.addEventListener('change', applyAlignStep);
  }
  applyAlignStep();
  fromInput();
})();
</script>";
        } elsif ($seg->{type} eq 'partition') {
            my $scheme = $seg->{scheme} || $pmap->{scheme} || 'UNKNOWN';
            my $is_boot = ($scheme eq 'GPT' && ($seg->{ptype} || '') eq 'freebsd-boot') ? 1 : 0;
            my $is_esp  = ($scheme eq 'GPT' && ($seg->{ptype} || '') eq 'efi') ? 1 : 0;

            my $dev = $seg->{dev} || '';
            my $mnt = $dev ? device_mountpoints($dev) : [];
            my $pools = $dev ? (device_in_zpool($dev) || []) : [];

            if (@$pools) {
                print &ui_alert(L("MSG_SEGMENT_IN_POOL", join(', ', @$pools)), "warning");
            }
            if (@$mnt) {
                print &ui_alert(L("MSG_SEGMENT_MOUNTED", join(', ', @$mnt)), "warning");
            }

            if ($is_boot) {
                print &ui_subheading(L("SUB_GPT_BOOTCODE"));
                print "<p>" . L("MSG_GPT_BOOTCODE_DESC") . "</p>";

                my $sig = gpt_bootcode_status($disk_name, $dev);
                my $selected_kind = ($in{'bootcode_kind'} && $in{'bootcode_kind'} eq 'ufs') ? 'gptboot' : 'gptzfsboot';
                if ($sig->{detected_bootcode} && $sig->{detected_bootcode} =~ /^(gptzfsboot|gptboot)$/) {
                    $selected_kind = $sig->{detected_bootcode};
                }
                my $actual_kind_sig = ($selected_kind eq 'gptboot')
                    ? ($sig->{actual_bootcode_gptboot} || '-')
                    : ($sig->{actual_bootcode_gptzfsboot} || '-');
                my @known_kind = grep { defined $_ && $_ ne '-' } (
                    ($selected_kind eq 'gptboot')
                        ? ($sig->{expected_bootcode_gptboot}, $sig->{system_bootcode_gptboot})
                        : ($sig->{expected_bootcode_gptzfsboot}, $sig->{system_bootcode_gptzfsboot})
                );
                my $kind_match = ($actual_kind_sig ne '-' && scalar(grep { $_ eq $actual_kind_sig } @known_kind)) ? 1 : 0;
                my $pmbr_match = 0;
                if (($sig->{actual_mbr} || '-') ne '-') {
                    my @known_pmbr = grep { defined $_ && $_ ne '-' } ($sig->{expected_mbr}, $sig->{system_mbr});
                    $pmbr_match = scalar(grep { $_ eq ($sig->{actual_mbr} || '-') } @known_pmbr) ? 1 : 0;
                }

                if ($sig->{state} eq 'error') {
                    my $err = $sig->{error} || L("VALUE_UNKNOWN");
                    print &ui_alert(L("ERR_BOOTCODE_STATUS_FAILED", $err), "danger");
                } elsif ($kind_match) {
                    my $kind_text = ($selected_kind eq 'gptboot') ? L("VALUE_BOOTCODE_UFS") : L("VALUE_BOOTCODE_ZFS");
                    print &ui_alert(L("MSG_BOOTCODE_UP_TO_DATE_KIND", $kind_text), "success");
                    if (!$pmbr_match) {
                        print &ui_alert(L("MSG_BOOTCODE_PMBR_INFO"), "info");
                    }
                } elsif ($sig->{state} eq 'unknown') {
                    print &ui_alert(L("MSG_BOOTCODE_UNKNOWN"), "info");
                } else {
                    my $kind_text = ($selected_kind eq 'gptboot') ? L("VALUE_BOOTCODE_UFS") : L("VALUE_BOOTCODE_ZFS");
                    print &ui_alert(L("MSG_BOOTCODE_OUTDATED_KIND", $kind_text), "warning");
                }

                if ($sig->{state} ne 'error') {
                    if (defined $sig->{boot_part_bytes} && $sig->{boot_part_bytes} =~ /^\d+$/) {
                        my $b = int($sig->{boot_part_bytes});
                        my $h = format_bytes($b);
                        print &ui_alert(L("MSG_BOOT_PART_SIZE", $h), "info");
                        if ($b < (180 * 1024)) {
                            print &ui_alert(L("WARN_BOOT_PART_TOO_SMALL"), "warning");
                        }
                        if ($b > (512 * 1024)) {
                            print &ui_alert(L("WARN_BOOT_PART_TOO_LARGE"), "warning");
                        }
                    }
                    if ($sig->{detected_bootcode}) {
                        my $kind = ($sig->{detected_bootcode} eq 'gptboot')
                            ? L("VALUE_BOOTCODE_UFS")
                            : L("VALUE_BOOTCODE_ZFS");
                        print &ui_alert(L("MSG_BOOTCODE_DETECTED", $kind), "info");
                    }

                    my @sig_heads = (
                        '',
                        L("COL_SIG_ACTUAL"),
                        L("COL_SIG_SHIPPED"),
                        L("COL_SIG_SYSTEM"),
                    );
                    my @sig_data = (
                        [
                            &html_escape(L("ROW_SIG_MBR")),
                            &html_escape($sig->{actual_mbr} || '-'),
                            &html_escape($sig->{expected_mbr} || '-'),
                            &html_escape($sig->{system_mbr} || '-'),
                        ],
                        [
                            &html_escape(L("ROW_SIG_BOOTCODE_GPTZFSBOOT")),
                            &html_escape($sig->{actual_bootcode_gptzfsboot} || '-'),
                            &html_escape($sig->{expected_bootcode_gptzfsboot} || '-'),
                            &html_escape($sig->{system_bootcode_gptzfsboot} || '-'),
                        ],
                        [
                            &html_escape(L("ROW_SIG_BOOTCODE_GPTBOOT")),
                            &html_escape($sig->{actual_bootcode_gptboot} || '-'),
                            &html_escape($sig->{expected_bootcode_gptboot} || '-'),
                            &html_escape($sig->{system_bootcode_gptboot} || '-'),
                        ],
                    );
                    print &ui_columns_table(\@sig_heads, 100, \@sig_data, undef, 1,
                        L("TABLE_BOOTCODE_SIGS"), L("VALUE_NONE"));
                }

                my $paths = bootcode_paths();
                my $have_shipped_pmbr = (-r $paths->{pmbr}) ? 1 : 0;
                my $have_shipped_zfs = (-r $paths->{gptzfsboot}) ? 1 : 0;
                my $have_shipped_ufs = (-r $paths->{gptboot}) ? 1 : 0;
                my $have_shipped = ($have_shipped_pmbr && ($have_shipped_zfs || $have_shipped_ufs)) ? 1 : 0;

                my $have_system_pmbr = (-r $paths->{system_pmbr}) ? 1 : 0;
                my $have_system_zfs = (-r $paths->{system_gptzfsboot}) ? 1 : 0;
                my $have_system_ufs = (-r $paths->{system_gptboot}) ? 1 : 0;
                my $have_system = ($have_system_pmbr && ($have_system_zfs || $have_system_ufs)) ? 1 : 0;

                if (!$have_shipped) {
                    print &ui_alert(L("MSG_BOOTCODE_SHIPPED_MISSING", $paths->{pmbr}, $paths->{gptzfsboot}, $paths->{gptboot}), "warning");
                }
                if (!$have_system) {
                    print &ui_alert(L("MSG_BOOTCODE_SYSTEM_MISSING", $paths->{system_pmbr}, $paths->{system_gptzfsboot}, $paths->{system_gptboot}), "warning");
                }
                if ($have_system) {
                    print &ui_alert(L("MSG_BOOTCODE_SOURCE_SYSTEM_RECOMMENDED"), "info");
                }

                print &ui_form_start("disks.cgi", "post");
                print &ui_hidden("action", "query");
                print &ui_hidden("disk", $disk_name);
                print &ui_hidden("seg", $seg_idx);
                print &ui_table_start(L("TABLE_BOOTCODE_ACTIONS"), "width=100%", 2);
                my $boot_kind_default = 'zfs';
                if ($sig->{detected_bootcode} && $sig->{detected_bootcode} eq 'gptboot') {
                    $boot_kind_default = 'ufs';
                }
                print &ui_table_row(L("ROW_BOOTCODE_KIND"),
                    &ui_select("bootcode_kind", $boot_kind_default, [
                        [ "zfs", L("OPT_BOOTCODE_ZFS") ],
                        [ "ufs", L("OPT_BOOTCODE_UFS") ],
                    ])
                );
                print &ui_table_row(L("ROW_CONFIRM_BOOTCODE_UPDATE"),
                    &ui_checkbox("confirm_bootcode_update", 1, L("LBL_CONFIRM_BOOTCODE_UPDATE"), 0));
                print &ui_table_row(L("ROW_CONFIRM_BOOTCODE_DESTROY"),
                    &ui_checkbox("confirm_bootcode_destroy", 1, L("LBL_CONFIRM_BOOTCODE_DESTROY"), 0));
                print &ui_table_end();

                my @buttons = ();
                push @buttons, [ "seg_update_bootcode_system", L("BTN_UPDATE_BOOTCODE_SYSTEM") ] if $have_system;
                push @buttons, [ "seg_update_bootcode", L("BTN_UPDATE_BOOTCODE") ] if $have_shipped;
                push @buttons, [ "seg_destroy_boot_partition", L("BTN_DESTROY_BOOT_PARTITION"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ];
                print &ui_form_end(\@buttons);
            } elsif ($is_esp) {
                print &ui_subheading(L("SUB_UEFI_ESP"));
                print "<p>" . L("MSG_UEFI_ESP_DESC") . "</p>";
                if ($dev) {
                    my $link = "uefi.cgi?action=manage&dev=" . &url_encode($dev);
                    print "<p><a class='button' href='" . &html_escape($link) . "'>" . &html_escape(L("BTN_MANAGE_ESP")) . "</a></p>";
                }
            } else {
                my @types = $scheme eq 'GPT'
                    ? qw(freebsd-zfs freebsd-swap freebsd-boot efi freebsd-ufs freebsd)
                    : qw(freebsd fat32);
                my %valid_type = map { $_ => 1 } @types;
                if ($seg->{ptype} && !$valid_type{$seg->{ptype}} && $seg->{ptype} =~ /^[A-Za-z0-9][A-Za-z0-9_\-\.]*$/) {
                    push @types, $seg->{ptype};
                }
                my @type_opts = map { [ $_, $_ ] } @types;

                print &ui_form_start("disks.cgi", "post");
                print &ui_hidden("action", "query");
                print &ui_hidden("disk", $disk_name);
                print &ui_hidden("seg", $seg_idx);
                print &ui_table_start(L("TABLE_PARTITION_ACTIONS"), "width=100%", 2);
                print &ui_table_row(L("ROW_PART_TYPE"), &ui_select("part_type", $seg->{ptype} || '', \@type_opts));
                if ($scheme eq 'GPT') {
                    my $cur_gpt_label = normalize_label_value($seg->{gpt_label});
                    my $rename_seed = $cur_gpt_label || segment_device_basename($seg) || '';
                    print &ui_table_row(L("ROW_PART_LABEL"), &ui_textbox("part_label", $cur_gpt_label, 20));
                    print &ui_table_row(L("ROW_PART_LABEL_RENAME"), &ui_textbox("part_label_rename", $rename_seed, 20));
                }
                my $selected_op = $in{'part_operation'} || 'none';
                print &ui_table_row(L("ROW_PART_OPERATION"),
                    &ui_select("part_operation", $selected_op, [
                        [ "none", L("OPT_PART_OP_NONE") ],
                        [ "resize", L("OPT_PART_OP_RESIZE") ],
                        [ "destroy", L("OPT_PART_OP_DESTROY") ],
                        [ "zerowrite", L("OPT_PART_OP_ZERO") ],
                        [ "randomwrite", L("OPT_PART_OP_RANDOM") ],
                        [ "trimerase", L("OPT_PART_OP_TRIM") ],
                    ]));
                my $wipe_warn_html = "<div id='part-wipe-warning' class='zfsguru-hidden'>" .
                    &ui_alert(L("MSG_PART_WIPE_WARNING"), "warning") .
                    "</div>";
                print &ui_table_span($wipe_warn_html);
                my $resize_max_hint = '';
                my $resize_max_sectors = 0;
                my $resize_align_step = 1;
                my $resize_align_label = 'SECT';
                if (defined($seg->{size}) && $seg->{size} =~ /^\d+$/) {
                    $resize_max_sectors = int($seg->{size});
                    if ($seg_idx >= 0 && $seg_idx < $#$segments) {
                        my $n = $segments->[$seg_idx + 1];
                        if ($n && ($n->{type}||'') =~ /^(free|unpartitioned)$/ && defined($n->{size}) && $n->{size} =~ /^\d+$/) {
                            $resize_max_sectors += int($n->{size});
                        }
                    }
                }
                if ($resize_max_sectors > 0) {
                    my $ss = ($info && $info->{sectorsize} && $info->{sectorsize} =~ /^\d+$/) ? int($info->{sectorsize}) : 512;
                    ($resize_align_step, $resize_align_label) = detect_partition_alignment($seg, $ss);
                    my $resize_max_bytes = $resize_max_sectors * $ss;
                    $resize_max_hint = L("HINT_PART_RESIZE_MAX", format_bytes($resize_max_bytes), $resize_max_sectors);
                    $resize_max_hint .= "<br>" . L("HINT_PART_RESIZE_ALIGN", $resize_align_label);
                    print "<input type='hidden' id='part-resize-max-sectors' value='" . int($resize_max_sectors) . "'>";
                    print "<input type='hidden' id='part-resize-sector-size' value='" . int($ss) . "'>";
                }
                my $resize_ui = &ui_textbox("part_resize", ($in{'part_resize'} // ''), 12);
                if ($resize_ui !~ /\bid=['"]part-resize-input['"]/i) {
                    $resize_ui =~ s/<input\b/<input id='part-resize-input'/i;
                }
                my $resize_slider_html = "";
                if ($resize_max_sectors > 0) {
                    my $cur_min = 1;
                    my $cur_val = (defined($seg->{size}) && $seg->{size} =~ /^\d+$/) ? int($seg->{size}) : $cur_min;
                    $cur_val = $cur_min if $cur_val < $cur_min;
                    $cur_val = $resize_max_sectors if $cur_val > $resize_max_sectors;
                    $resize_slider_html =
                        "<div id='part-resize-slider-wrap' style='margin-top:6px'>"
                      . "<input type='range' id='part-resize-slider' min='$cur_min' max='$resize_max_sectors' step='$resize_align_step' value='$cur_val' style='width:320px;vertical-align:middle' "
                      . "oninput=\"(function(s){var v=s.value;var i=document.getElementById('part-resize-input');if(i){i.value=v;}var l=document.getElementById('part-resize-slider-value');if(l){l.textContent=v+' " . L("UNIT_SECTORS") . "';}})(this)\"> "
                      . "<span id='part-resize-slider-value'>" . int($cur_val) . " " . L("UNIT_SECTORS") . "</span>"
                      . "<br><small>" . &html_escape(L("HINT_PART_RESIZE_SLIDER")) . "</small>"
                      . "</div>";
                }
                print &ui_table_row(L("ROW_PART_RESIZE"), $resize_ui . $resize_slider_html,
                    1, undef, [ "id='part-resize-row'", "zfsguru-hidden" ]);
                print &ui_table_span(
                    "<div id='part-resize-hint' class='zfsguru-hidden'><small id='part-resize-hint-text'>" .
                    &html_escape($resize_max_hint || L("HINT_PART_RESIZE_MAX_UNKNOWN")) .
                    "</small><div id='part-resize-check' class='zfsguru-muted'></div></div>"
                );
                print &ui_table_row(L("ROW_CONFIRM_PART"),
                    &ui_checkbox("confirm_part", 1, L("LBL_CONFIRM_PART"), 0));
                print &ui_table_row(L("ROW_CONFIRM_PART_WIPE"),
                    &ui_checkbox("confirm_part_wipe", 1, L("LBL_CONFIRM_PART_WIPE"), 0),
                    1, undef, [ "id='part-wipe-confirm-row'", "zfsguru-hidden" ]);
                print &ui_table_row(L("ROW_WIPE_BACKGROUND"),
                    &ui_checkbox("part_wipe_background", 1, L("LBL_WIPE_BACKGROUND"), 0),
                    1, undef, [ "id='part-wipe-background-row'", "zfsguru-hidden" ]);
                if ($scheme eq 'GPT') {
                    print &ui_table_row(L("ROW_CONFIRM_PART_LABEL"),
                        &ui_checkbox("confirm_part_label", 1, L("LBL_CONFIRM_PART_LABEL"), 0));
                }
                print &ui_table_end();
                my @part_buttons = ();
                if ($scheme eq 'GPT') {
                    push @part_buttons, [ "seg_rename_partition_label", L("BTN_RENAME_PART_LABEL"), undef, 0, "style='background:#0275d8;color:#fff;border-color:#0275d8'" ];
                }
                push @part_buttons, [ "seg_update_partition", L("BTN_APPLY_PARTITION"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ];
                print &ui_form_end(\@part_buttons);
                print "<script>
(function(){
  function byName(n){ return document.querySelector('[name=\"'+n+'\"]'); }
  function el(id){ return document.getElementById(id); }
  function toggle(){
    var op = byName('part_operation');
    if(!op) return;
    var v = op.value || 'none';
    var isResize = (v === 'resize');
    var isWipe = (v === 'zerowrite' || v === 'randomwrite' || v === 'trimerase');
    var rr = el('part-resize-row');
    var rh = el('part-resize-hint');
    var wr = el('part-wipe-confirm-row');
    var br = el('part-wipe-background-row');
    var ww = el('part-wipe-warning');
    if(rr){ rr.classList[isResize ? 'remove' : 'add']('zfsguru-hidden'); }
    if(rh){ rh.classList[isResize ? 'remove' : 'add']('zfsguru-hidden'); }
    if(wr){ wr.classList[isWipe ? 'remove' : 'add']('zfsguru-hidden'); }
    if(br){ br.classList[isWipe ? 'remove' : 'add']('zfsguru-hidden'); }
    if(ww){ ww.classList[isWipe ? 'remove' : 'add']('zfsguru-hidden'); }
  }
  function parseToSectors(v, ss){
    if(!v) return null;
    v = String(v).trim();
    if(!v) return null;
    if(/^[0-9]+$/.test(v)) return parseInt(v,10);
    var m = v.match(/^([0-9]+(?:\\.[0-9]+)?)([KMGTP])$/i);
    if(!m) return null;
    var n = parseFloat(m[1]);
    var u = m[2].toUpperCase();
    var p = {K:1,M:2,G:3,T:4,P:5}[u] || 0;
    var bytes = n * Math.pow(1024,p);
    return Math.ceil(bytes / ss);
  }
  function updateResizeCheck(){
    var inEl = el('part-resize-input') || byName('part_resize');
    var outEl = el('part-resize-check');
    var maxEl = el('part-resize-max-sectors');
    var ssEl = el('part-resize-sector-size');
    if(!inEl || !outEl || !maxEl || !ssEl){ return; }
    var maxS = parseInt(maxEl.value || '0', 10);
    var ss = parseInt(ssEl.value || '512', 10);
    var req = parseToSectors(inEl.value, ss);
    if(req === null){
      outEl.textContent = '';
      return;
    }
    if(maxS > 0 && req > maxS){
      outEl.style.color = '#b94a48';
      outEl.textContent = 'Requested size exceeds maximum allowed for this partition position.';
    } else if(maxS > 0) {
      outEl.style.color = '#3c763d';
      outEl.textContent = 'Requested size is within the available maximum.';
    } else {
      outEl.style.color = '';
      outEl.textContent = '';
    }
  }
  function bindResizeSlider(){
    var inEl = el('part-resize-input') || byName('part_resize');
    var slider = el('part-resize-slider');
    var label = el('part-resize-slider-value');
    if(!inEl || !slider || !label){ return; }
    var ssEl = el('part-resize-sector-size');
    var ss = ssEl ? parseInt(ssEl.value || '512', 10) : 512;
    var currentStep = parseInt(slider.step || '1', 10);
    if(!currentStep || currentStep < 1){ currentStep = 1; }
    function snapToStep(v, step, min, max){
      if(step <= 1) return Math.max(min, Math.min(max, v));
      var n = Math.floor(v / step) * step;
      if(n < step) n = step;
      if(n < min) n = min;
      if(n > max) n = max;
      return n;
    }
    function humanFromSectors(sec){
      var bytes = sec * ss;
      var gib = bytes / (1024*1024*1024);
      if (gib >= 1) {
        return gib.toFixed(2) + ' GiB';
      }
      var mib = bytes / (1024*1024);
      return mib.toFixed(2) + ' MiB';
    }
    function renderLabel(sec){
      label.textContent = sec + ' sectors (~' + humanFromSectors(sec) + ')';
    }
    var updateFromSlider = function(){
      var min = parseInt(slider.min || '1', 10);
      var max = parseInt(slider.max || '1', 10);
      var v = parseInt(slider.value || '1', 10);
      v = snapToStep(v, currentStep, min, max);
      slider.value = String(v);
      inEl.value = String(v);
      renderLabel(v);
      updateResizeCheck();
    };
    var updateFromInput = function(){
      var v = String(inEl.value || '').trim();
      var n = parseToSectors(v, ss);
      if(n !== null){
        var min = parseInt(slider.min || '1', 10);
        var max = parseInt(slider.max || '1', 10);
        n = snapToStep(n, currentStep, min, max);
        slider.value = String(n);
        inEl.value = String(n);
        renderLabel(n);
      }
      updateResizeCheck();
    };
    slider.addEventListener('input', updateFromSlider);
    slider.addEventListener('change', updateFromSlider);
    inEl.addEventListener('input', updateFromInput);
    inEl.addEventListener('change', updateFromInput);
    var form = slider.closest ? slider.closest('form') : null;
    if(form){
      form.addEventListener('submit', function(){
        inEl.value = String(slider.value || inEl.value || '');
      });
    }
    updateFromInput();
  }
  var op = byName('part_operation');
  if(op){
    op.addEventListener('change', toggle);
    toggle();
  }
  var rs = el('part-resize-input') || byName('part_resize');
  if(rs){
    rs.addEventListener('input', updateResizeCheck);
    rs.addEventListener('change', updateResizeCheck);
    updateResizeCheck();
  }
  bindResizeSlider();
})();
</script>";

                if ($scheme eq 'MBR') {
                    my $active = $seg->{mbr_active};
                    my $status = defined $active ? ($active ? L("VALUE_ACTIVE") : L("VALUE_INACTIVE")) : L("VALUE_UNKNOWN");
                    my $supports_unset = gpart_supports_subcommand('unset') ? 1 : 0;
                    print &ui_hr();
                    print &ui_subheading(L("SUB_MBR_ACTIVE"));
                    print "<p>" . L("MSG_MBR_ACTIVE_DESC") . "</p>";
                    print &ui_alert(L("MSG_MBR_ACTIVE_WARNING"), "warning") if !$active;
                    print &ui_form_start("disks.cgi", "post");
                    print &ui_hidden("action", "query");
                    print &ui_hidden("disk", $disk_name);
                    print &ui_hidden("seg", $seg_idx);
                    print &ui_table_start(L("TABLE_MBR_ACTIVE"), "width=100%", 2);
                    print &ui_table_row(L("ROW_MBR_ACTIVE_STATUS"), &html_escape($status));
                    print &ui_table_row(L("ROW_CONFIRM_MBR_ACTIVE"),
                        &ui_checkbox("confirm_mbr_active", 1, L("LBL_CONFIRM_MBR_ACTIVE"), 0));
                    print &ui_table_end();
                    my @btns = ();
                    push @btns, [ "seg_set_mbr_active", L("BTN_MBR_SET_ACTIVE") ] if !$active;
                    push @btns, [ "seg_unset_mbr_active", L("BTN_MBR_UNSET_ACTIVE") ] if ($active && $supports_unset);
                    if ($active && !$supports_unset) {
                        print &ui_alert(L("MSG_GPART_UNSET_UNSUPPORTED"), "info");
                    }
                    print &ui_form_end(\@btns);
                }
            }
        }

    } else {
        print "<p>" . L("MSG_SEGMENT_SELECT_HINT") . "</p>";
    }

    if ($scheme_corrupt) {
        print &ui_hr();
        print &ui_alert(L("MSG_SCHEME_CORRUPT_DETECTED"), "warning");
        print &ui_subheading(L("SUB_RECOVER_SCHEME"));
        print "<p>" . L("MSG_SCHEME_CORRUPT_ACTION") . "</p>";
        print &ui_form_start("disks.cgi", "post");
        print &ui_hidden("action", "query");
        print &ui_hidden("disk", $disk_name);
        print &ui_table_start(L("TABLE_RECOVER_SCHEME"), "width=100%", 2);
        print &ui_table_row(L("ROW_CONFIRM_SCHEME_RECOVER"),
            &ui_checkbox("confirm_scheme_recover", 1, L("LBL_CONFIRM_SCHEME_RECOVER"), 0));
        print &ui_table_end();
        print &ui_form_end([ [ "seg_recover_scheme", L("BTN_RECOVER_SCHEME") ] ]);
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_DISK_QUERY_GPART", $disk_name));
    if (defined $gpart) {
        print "<pre>" . &html_escape($gpart) . "</pre>";
    } else {
        print &ui_print_error(L("ERR_GPART_SHOW_FAILED", $disk_name));
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_SCHEME_BACKUP_RESTORE"));

    # Backup is read-only, safe in non-advanced mode.
    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "query");
    print &ui_hidden("disk", $disk_name);
    print &ui_hidden("seg", $seg_idx) if $seg_idx >= 0;
    print &ui_table_start(L("TABLE_SCHEME_BACKUP"), "width=100%", 2);
    print &ui_table_row(L("ROW_SCHEME_BACKUP_OUTPUT"),
        &ui_textarea("scheme_backup_output", $scheme_backup_out, 8, 100, "off", 0, "readonly"));
    print &ui_table_end();
    print &ui_form_end([ [ "scheme_backup", L("BTN_SCHEME_BACKUP") ] ]);

    if ($advanced_enabled) {
        print &ui_hr();
        print &ui_form_start("disks.cgi", "post");
        print &ui_hidden("action", "query");
        print &ui_hidden("disk", $disk_name);
        print &ui_hidden("seg", $seg_idx) if $seg_idx >= 0;
        print &ui_table_start(L("TABLE_SCHEME_RESTORE"), "width=100%", 2);
        print &ui_table_row(L("ROW_SCHEME_RESTORE_DATA"),
            &ui_textarea("scheme_restore_data", ($in{'scheme_restore_data'} // ''), 8, 100));
        print &ui_table_row(L("ROW_SCHEME_RESTORE_FORCE"),
            &ui_checkbox("scheme_restore_force", 1, L("LBL_SCHEME_RESTORE_FORCE"), ($in{'scheme_restore_force'} ? 1 : 0)) .
            "<br><small>" . L("HINT_SCHEME_RESTORE_FORCE") . "</small>");
        print &ui_table_row(L("ROW_CONFIRM_SCHEME_RESTORE"),
            &ui_checkbox("confirm_scheme_restore", 1, L("LBL_CONFIRM_SCHEME_RESTORE"), ($in{'confirm_scheme_restore'} ? 1 : 0)));
        print &ui_table_row(L("ROW_CONFIRM_SCHEME_RESTORE_FORCE"),
            &ui_checkbox("confirm_scheme_restore_force", 1, L("LBL_CONFIRM_SCHEME_RESTORE_FORCE"), ($in{'confirm_scheme_restore_force'} ? 1 : 0)));
        print &ui_table_end();
        print &ui_form_end([ [ "scheme_restore", L("BTN_SCHEME_RESTORE"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ] ]);
    }

    if ($pmap->{scheme} && $pmap->{scheme} ne 'NONE' && $pmap->{scheme} ne 'UNKNOWN') {
        print &ui_hr();
        print &ui_form_start("disks.cgi", "post");
        print &ui_hidden("action", "query");
        print &ui_hidden("disk", $disk_name);
        print &ui_table_start(L("TABLE_DESTROY_WHOLE_SCHEME"), "width=100%", 2);
        print &ui_table_row(L("ROW_CONFIRM_SCHEME_DESTROY"),
            &ui_checkbox("confirm_scheme_destroy", 1, L("LBL_CONFIRM_SCHEME_DESTROY"), 0));
        print &ui_table_end();
        print &ui_form_end([ [ "seg_destroy_scheme", L("BTN_DESTROY_SCHEME"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ] ]);
    }

    my @wipe_targets;
    push @wipe_targets, [ "/dev/$disk_name", "/dev/$disk_name" ];
    for my $p (glob("/dev/${disk_name}p*")) {
        push @wipe_targets, [ $p, $p ];
    }
    for my $s (glob("/dev/${disk_name}s*")) {
        push @wipe_targets, [ $s, $s ];
    }
    my $labels = glabel_list();
    for my $l (@$labels) {
        next unless $l->{device} && $l->{device} =~ /^\Q$disk_name\E/;
        my $path = "/dev/" . $l->{label};
        push @wipe_targets, [ $path, $path ];
    }
    my %seen;
    @wipe_targets = grep { !$seen{$_->[0]}++ } @wipe_targets;

    print &ui_hr();
    print &ui_subheading(L("SUB_DISK_WIPE"));
    if ($advanced_enabled) {
        my $blkdiscard_supported = command_exists($zfsguru_lib::BLKDISCARD);
        my ($ata_supported, $ata_why) = ata_secure_erase_available();
        my $ata_mode = $config{'ata_secure_erase_mode'} || 'normal';
        my $ata_mode_label = ($ata_mode eq 'enhanced')
            ? L("OPT_ATA_MODE_ENHANCED")
            : L("OPT_ATA_MODE_NORMAL");
        my $ata_pass_state = ($config{'ata_secure_erase_pass'} && length $config{'ata_secure_erase_pass'})
            ? L("VALUE_CONFIGURED")
            : L("VALUE_NOT_CONFIGURED");
        my $blkdiscard_state = $blkdiscard_supported
            ? (L("VALUE_ENABLED") . " (" . &html_escape($zfsguru_lib::BLKDISCARD) . ")")
            : L("VALUE_DISABLED");
        print &ui_alert(L("MSG_WIPE_WARNING"), "warning");
        print &ui_form_start("disks.cgi", "post");
        print &ui_hidden("action", "query");
        print &ui_hidden("disk", $disk_name);
        print &ui_table_start(L("TABLE_DISK_WIPE"), "width=100%", 2);
        print &ui_table_row(L("ROW_WIPE_TARGET"), &ui_select("wipe_target", "/dev/$disk_name", \@wipe_targets));
        print &ui_table_row(L("ROW_WIPE_MODE"), &ui_select("wipe_mode", "full", [
            [ "full", L("OPT_WIPE_FULL") ],
            [ "quick", L("OPT_WIPE_QUICK") ],
        ]));
        my $quick_warn_html = "<div id='wipe-mode-warning' class='zfsguru-hidden'>" .
            &ui_alert(L("MSG_WIPE_QUICK_ONLY_ZERO_WARN"), "info") .
            "</div>";
        print &ui_table_span($quick_warn_html);
        if ($ata_supported) {
            print &ui_table_row(L("ROW_WIPE_ATA_MODE"), $ata_mode_label);
            print &ui_table_row(L("ROW_WIPE_ATA_PASS"), $ata_pass_state);
            print &ui_table_row(L("ROW_WIPE_ATA_CONFIG"), L("MSG_WIPE_ATA_CONFIG_HINT"));
        }
        print &ui_table_row(L("ROW_WIPE_DISCARD_STATUS"), $blkdiscard_state);
        print &ui_table_row(
            L("ROW_WIPE_SIZE"),
            &ui_textbox("wipe_mib", "16", 6) . " " . L("UNIT_MIB"),
            1, undef, [ "id='wipe-size-row'", "zfsguru-hidden" ]
        );
        print &ui_table_row(L("ROW_CONFIRM_WIPE"),
            &ui_checkbox("confirm_wipe", 1, L("LBL_CONFIRM_WIPE_TARGET"), 0));
        print &ui_table_row(L("ROW_CONFIRM_WIPE_IN_USE"),
            &ui_checkbox("confirm_wipe_in_use", 1, L("LBL_CONFIRM_WIPE_IN_USE"), 0));
        print &ui_table_row(
            L("ROW_CONFIRM_SECURE"),
            &ui_checkbox("confirm_secure", 1, L("LBL_CONFIRM_SECURE_WIPE"), 0),
            1, undef, [ "id='wipe-confirm-secure-row'" ]
        );
        print &ui_table_row(L("ROW_WIPE_BACKGROUND"),
            &ui_checkbox("wipe_background", 1, L("LBL_WIPE_BACKGROUND"), 0));
        print &ui_table_end();
        my $wipe_danger_style = "style='background:#d9534f;color:#fff;border-color:#d9534f'";
        my @wipe_buttons = (
            [ "wipe_zero",   L("BTN_WIPE_ZERO"),   undef, 0, $wipe_danger_style ],
            [ "wipe_random", L("BTN_WIPE_RANDOM"), undef, 0, $wipe_danger_style ],
            [ "wipe_secure", L("BTN_WIPE_SECURE"), undef, 0, $wipe_danger_style ],
        );
        if ($ata_supported) {
            push @wipe_buttons, [ "wipe_ata", L("BTN_WIPE_ATA"), undef, 0, $wipe_danger_style ];
        } else {
            print &ui_alert(L("MSG_WIPE_ATA_UNAVAILABLE") . ($ata_why ? " " . &html_escape($ata_why) : ""), "info");
        }
        if ($blkdiscard_supported) {
            push @wipe_buttons, [ "wipe_discard", L("BTN_WIPE_DISCARD") ];
        } else {
            print &ui_alert(L("MSG_WIPE_DISCARD_UNAVAILABLE"), "info");
        }
        print &ui_form_end(\@wipe_buttons);
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_BG_JOBS"));
    print "<p class='zfsguru-muted'>" . L("MSG_BG_JOBS_RECENT_ONLY") . "</p>";
    my $jobs = zfsguru_list_jobs(limit => 25) || [];
    my @job_heads = (L("COL_JOB"), L("COL_STATUS"), L("COL_UPDATED"), L("COL_ACTIONS"));
    my @job_data;
    for my $j (@$jobs) {
        my $raw_st = ($j->{status} || '');
        my $st = $raw_st eq 'ok' ? L("VALUE_JOB_DONE")
            : $raw_st eq 'failed' ? L("VALUE_JOB_FAILED")
            : $raw_st eq 'killed' ? L("VALUE_JOB_KILLED")
            : $raw_st eq 'stale' ? L("VALUE_JOB_STALE")
            : L("VALUE_JOB_RUNNING");
        my $st_class =
            $st eq L("VALUE_JOB_DONE")    ? 'zfsguru-status-ok' :
            $st eq L("VALUE_JOB_FAILED")  ? 'zfsguru-status-bad' :
            $st eq L("VALUE_JOB_KILLED")  ? 'zfsguru-status-bad' :
            $st eq L("VALUE_JOB_STALE")   ? 'zfsguru-status-warn' :
            $st eq L("VALUE_JOB_RUNNING") ? 'zfsguru-status-warn' :
                                            'zfsguru-status-unknown';

        my $view = &ui_link_icon(
            "disks.cgi?action=job_log&job=" . &url_encode($j->{file}) . "&disk=" . &url_encode($disk_name),
            L("BTN_VIEW_LOG"),
            undef,
            { class => 'primary' }
        );
        my $kill = '';
        if ($raw_st eq 'running') {
            $kill = "<form method='post' action='disks.cgi' style='display:inline;margin-left:6px'>"
                  . &ui_hidden("action", "query")
                  . &ui_hidden("disk", $disk_name)
                  . &ui_hidden("kill_bg_job", $j->{file})
                  . "<input type='submit' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                  . "' style='background:#d9534f;color:#fff;border-color:#d9534f'>"
                  . "</form>";
        } else {
            $kill = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                  . "' disabled='disabled' title='" . &html_escape(L("MSG_JOB_NOT_RUNNING"))
                  . "' style='margin-left:6px;background:#d9534f;color:#fff;border-color:#d9534f;opacity:.45;cursor:not-allowed'>";
        }
        push @job_data, [
            &html_escape($j->{file}),
            "<span class='$st_class'>" . &html_escape($st) . "</span>",
            &html_escape($j->{mtime} || '-'),
            $view . $kill,
        ];
    }
    # Force empty table title to avoid duplicate heading rendering in some themes.
    print &ui_columns_table(\@job_heads, 100, \@job_data, undef, 1,
        '', L("VALUE_NONE"));
    print "<p>";
    print &ui_link_icon("disks.cgi?action=query&disk=" . &url_encode($disk_name), L("BTN_REFRESH"), undef, { class => 'primary' });
    print " ";
    print &ui_form_start("disks.cgi", "post", "style='display:inline'");
    print &ui_hidden("action", "query");
    print &ui_hidden("disk", $disk_name);
    print &ui_form_end([
        [ "clear_bg_logs", L("BTN_EMPTY_LOGS"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ],
    ]);
    print "</p>";

    print "<p>" .
          &ui_link_icon("disks.cgi?action=format&disk=" . &url_encode($disk_name), L("BTN_OPEN_FORMAT"), undef, { class => 'default' }) .
          "</p>";
}

sub action_format {
    my $disk_name = $in{'disk'};
    return unless $disk_name;

    my %diskset = map { $_ => 1 } @{ disk_list() || [] };
    if (!$diskset{$disk_name}) {
        print &ui_print_error(L("ERR_DISK_INVALID", $disk_name));
        return;
    }

    my $dinfo = diskinfo($disk_name) || {};
    my $dev_path = "/dev/$disk_name";
    my $mnts = device_mountpoints($dev_path) || [];
    my @pool_targets = ($dev_path);
    push @pool_targets, glob("/dev/${disk_name}p*");
    push @pool_targets, glob("/dev/${disk_name}s*");
    my $gpt_map = disk_gpt_labels_map([ $disk_name ]) || {};
    if (ref($gpt_map) eq 'HASH' && ref($gpt_map->{$disk_name}) eq 'ARRAY') {
        for my $lbl (@{ $gpt_map->{$disk_name} || [] }) {
            next unless defined $lbl && $lbl ne '';
            push @pool_targets, "/dev/gpt/$lbl";
        }
    }
    my $geom_map = disk_geom_labels_map() || {};
    if (ref($geom_map) eq 'HASH' && ref($geom_map->{$disk_name}) eq 'ARRAY') {
        for my $lbl (@{ $geom_map->{$disk_name} || [] }) {
            next unless defined $lbl && $lbl ne '';
            push @pool_targets, "/dev/label/$lbl";
        }
    }
    my $labels = glabel_list() || [];
    for my $l (@$labels) {
        next unless ref($l) eq 'HASH';
        my $prov = $l->{provider} || $l->{device} || '';
        my $name = $l->{name} || $l->{label} || '';
        next unless $prov ne '' && $name ne '';
        $prov =~ s{^/dev/}{};
        if ($prov =~ /^\Q$disk_name\E(?:p|s)\d+$/ || $prov eq $disk_name) {
            push @pool_targets, "/dev/$name";
        }
    }
    my %seen_pt;
    @pool_targets = grep { defined($_) && $_ ne '' && !$seen_pt{$_}++ } @pool_targets;
    my %pool_seen;
    for my $t (@pool_targets) {
        my $pl = device_in_zpool($t) || [];
        $pool_seen{$_} = 1 for @$pl;
    }
    my $pools = [ sort keys %pool_seen ];
    
    if ($in{'do_format'}) {
        my $scheme = $in{'partition_scheme'} || 'gpt';
        
        if ($in{'confirm'}) {
            # This is dangerous, so we require explicit confirmation
            print &ui_print_error_header(L("HDR_FORMATTING_DISK"));
            print L("MSG_FORMATTING_IN_PROGRESS");
            
            my @cmd;
            if ($in{'wipe_ptable'}) {
                if (!$in{'confirm_wipe'}) {
                    print &ui_print_error(L("ERR_CONFIRM_WIPE_REQUIRED"));
                    return;
                }
                my $mib = $in{'wipe_mib'} || 16;
                my ($ok, $err) = disk_wipe_head($disk_name, $mib);
                if (!$ok) {
                    print &ui_print_error(L("ERR_WIPE_FAILED", $err || 'wipe failed'));
                    return;
                }
            }
            if ($in{'destroy_existing'}) {
                my ($drc, $dout, $derr) = run_cmd($zfsguru_lib::GPART || '/sbin/gpart', 'destroy', '-F', $dev_path);
                if ($drc != 0) {
                    print &ui_alert("Partition table destroy returned non-zero (continuing): " . &html_escape($derr || $dout || 'unknown'), "warning");
                }
            }

            if ($scheme eq 'gpt') {
                @cmd = ($zfsguru_lib::GPART || '/sbin/gpart', 'create', '-s', 'gpt', $dev_path);
            } elsif ($scheme eq 'mbr') {
                @cmd = ($zfsguru_lib::GPART || '/sbin/gpart', 'create', '-s', 'mbr', $dev_path);
            }
            
            my ($rc, $out, $err) = run_cmd(@cmd);
            if ($rc == 0) {
                if ($scheme eq 'gpt' && $in{'create_boot_part'}) {
                    my ($brc, $bout, $berr) = run_cmd($zfsguru_lib::GPART || '/sbin/gpart', 'add',
                        '-b', '64',
                        '-s', '512K',
                        '-t', 'freebsd-boot',
                        $dev_path
                    );
                    if ($brc != 0) {
                        print &ui_alert("Failed to create GPT boot partition: " . &html_escape($berr || $bout || 'unknown'), "warning");
                    } else {
                        print &ui_print_success("GPT boot partition created.");
                        if ($in{'install_bootcode'}) {
                            my $boot_idx = 1;
                            if (defined $bout && $bout =~ /\b\Q$disk_name\Ep(\d+)\b/) {
                                $boot_idx = int($1);
                            }
                            my $paths = bootcode_paths();
                            my $kind = ($in{'bootcode_kind'} && $in{'bootcode_kind'} eq 'ufs') ? 'ufs' : 'zfs';
                            my $boot_key = ($kind eq 'ufs') ? 'gptboot' : 'gptzfsboot';
                            my $pmbr = (-r $paths->{system_pmbr}) ? $paths->{system_pmbr} : $paths->{pmbr};
                            my $bootcode = (-r $paths->{"system_$boot_key"}) ? $paths->{"system_$boot_key"} : $paths->{$boot_key};
                            if (!$pmbr || !$bootcode || !-r $pmbr || !-r $bootcode) {
                                print &ui_alert("Bootcode files missing, skipping bootcode install.", "warning");
                            } else {
                                my ($crc, $cout, $cerr) = run_cmd($zfsguru_lib::GPART || '/sbin/gpart', 'bootcode',
                                    '-b', $pmbr,
                                    '-p', $bootcode,
                                    '-i', $boot_idx,
                                    $dev_path
                                );
                                if ($crc != 0) {
                                    print &ui_alert("Failed to install bootcode: " . &html_escape($cerr || $cout || 'unknown'), "warning");
                                } else {
                                    print &ui_print_success("GPT bootcode installed.");
                                }
                            }
                        }
                    }
                }
                print &ui_print_success(L("SUCCESS_DISK_FORMATTED"));
                log_info("Formatted disk $disk_name with $scheme scheme");
            } else {
                print &ui_print_error(L("ERR_DISK_FORMAT_FAILED", $err));
            }
            return;
        }
        
        print &ui_print_error_header(L("HDR_DESTRUCTIVE_OPERATION"));
        print "<p>" . L("MSG_FORMAT_DISK_CONFIRM", $disk_name, $scheme) . "</p>";
        print "<p><b>" . L("MSG_ERASE_ALL_DATA") . "</b></p>";
        
        print &ui_form_start("disks.cgi", "post");
        print &ui_hidden("action", "format");
        print &ui_hidden("disk", $disk_name);
        print &ui_hidden("do_format", 1);
        print &ui_hidden("partition_scheme", $scheme);
        print &ui_hidden("destroy_existing", ($in{'destroy_existing'} ? 1 : 0));
        print &ui_hidden("create_boot_part", ($in{'create_boot_part'} ? 1 : 0));
        print &ui_hidden("install_bootcode", ($in{'install_bootcode'} ? 1 : 0));
        print &ui_hidden("bootcode_kind", ($in{'bootcode_kind'} || 'zfs'));
        if ($in{'wipe_ptable'}) {
            print &ui_hidden("wipe_ptable", 1);
            print &ui_hidden("wipe_mib", $in{'wipe_mib'} || 16);
            print &ui_hidden("confirm_wipe", $in{'confirm_wipe'} || 0);
        }
        # rely on the submit button name to set the confirmation flag
        print &ui_form_end([
            [ "confirm", L("BTN_YES_FORMAT_DISK"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ],
            [ "", L("BTN_CANCEL") ],
        ]);
        return;
    }
    
    print &ui_subheading(L("SUB_FORMAT_DISK", $disk_name));
    print &ui_table_start("Format Quick Info", "width=100%", 2);
    print &ui_table_row("Disk", &html_escape($disk_name));
    print &ui_table_row("Device Path", &html_escape($dev_path));
    print &ui_table_row("Media Size", (defined $dinfo->{mediasize} ? format_bytes($dinfo->{mediasize}) : L("VALUE_UNKNOWN")));
    print &ui_table_row("Current Mountpoints", @$mnts ? &html_escape(join(", ", @$mnts)) : L("VALUE_NONE"));
    print &ui_table_row("Pool Membership", @$pools ? &html_escape(join(", ", @$pools)) : L("VALUE_NONE"));
    print &ui_table_end();
    if (@$mnts || @$pools) {
        print &ui_alert("This disk appears mounted and/or part of a pool. Formatting can break active services.", "warning");
    }

    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "format");
    print &ui_hidden("disk", $disk_name);
    print &ui_hidden("do_format", 1);
    
    print &ui_table_start(L("TABLE_FORMAT_CONFIG"), "width=100%", 2);
    print &ui_table_row(L("COL_DISK"), $disk_name);
    print &ui_table_row(L("ROW_PARTITION_SCHEME"), &ui_select("partition_scheme", "gpt", [
        [ "gpt", L("OPT_GPT_RECOMMENDED") ],
        [ "mbr", L("OPT_MBR_LEGACY") ],
    ]));
    print &ui_table_row("Destroy Existing Partition Table First",
        &ui_checkbox("destroy_existing", 1, "Use gpart destroy -F before create", 1));
    print &ui_table_row(L("ROW_WIPE_PTABLE"),
        &ui_checkbox("wipe_ptable", 1, L("LBL_WIPE_PTABLE"), 0) . " " .
        L("MSG_WIPE_PTABLE_NOTE"));
    print &ui_table_row(L("ROW_WIPE_SIZE"),
        &ui_textbox("wipe_mib", "16", 6) . " " . L("UNIT_MIB"));
    print &ui_table_row(L("ROW_CONFIRM_WIPE"),
        &ui_checkbox("confirm_wipe", 1, L("LBL_CONFIRM_WIPE"), 0));
    print &ui_table_row("Create GPT Boot Partition (512K freebsd-boot)",
        &ui_checkbox("create_boot_part", 1, "Recommended for bootable GPT disks", 0));
    print &ui_table_row("Install GPT Bootcode",
        &ui_checkbox("install_bootcode", 1, "Install PMBR + gptzfsboot/gptboot after creating boot partition", 0));
    print &ui_table_row("Bootcode Type",
        &ui_select("bootcode_kind", "zfs", [
            [ "zfs", "zfs (gptzfsboot)" ],
            [ "ufs", "ufs (gptboot)" ],
        ]));
    print &ui_table_end();
    
    print &ui_form_end([ [ "do_format", L("BTN_PROCEED"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ] ]);
}

sub action_advanced {
    print &ui_subheading(L("SUB_DISK_ADVANCED"));

    my $disks = disk_list();
    my %diskset = map { $_ => 1 } @$disks;
    my $query = $in{'disk'} || $in{'query'} || '';
    $query = '' unless $diskset{$query};

    my $adv_link = "disks.cgi?action=advanced";
    $adv_link .= "&disk=" . &url_encode($query) if $query ne '';
    my $mon_link = "disks.cgi?action=monitor&filter=" . &url_encode('^(gpt|label)/');
    my $smart_link = "disks.cgi?action=smart";
    $smart_link .= "&disk=" . &url_encode($query) if $query ne '';
    my $query_link = $query ne '' ? "disks.cgi?action=query&disk=" . &url_encode($query) : '';
    print &ui_table_start("Quick Actions", "width=100%", 2);
    print &ui_table_row("Selected Disk", $query ne '' ? &html_escape($query) : "none");
    print &ui_table_row("Actions",
        &ui_link_icon($adv_link, "Refresh Advanced", undef, { class => 'primary' }) . " " .
        &ui_link_icon($smart_link, "Open SMART", undef, { class => 'default' }) . " " .
        &ui_link_icon($mon_link, "Open I/O Monitor", undef, { class => 'default' }) .
        ($query_link ne '' ? (" " . &ui_link_icon($query_link, "Open Partition Modify", undef, { class => 'default' })) : ""));
    print &ui_table_end();

    for my $key (keys %in) {
        if ($key =~ /^spindown_(.+)$/) {
            my $disk_name = $1;
            next unless $diskset{$disk_name};
            if (disk_spindown($disk_name)) {
                print &ui_print_success(L("SUCCESS_DISK_SPINDOWN", $disk_name));
            } else {
                print &ui_print_error(L("ERR_DISK_SPINDOWN_FAILED", $disk_name));
            }
        } elsif ($key =~ /^spinup_(.+)$/) {
            my $disk_name = $1;
            next unless $diskset{$disk_name};
            if (disk_spinup($disk_name)) {
                print &ui_print_success(L("SUCCESS_DISK_SPINUP", $disk_name));
            } else {
                print &ui_print_error(L("ERR_DISK_SPINUP_FAILED", $disk_name));
            }
        }
    }

    if ($in{'apm_submit'}) {
        my $disk_name = $in{'apm_setting_disk'} || '';
        my $level = $in{'apm_newsetting'} || '';
        if (!$diskset{$disk_name}) {
            print &ui_print_error(L("ERR_DISK_INVALID", $disk_name));
        } elsif ($level !~ /^\d+$/ || $level < 1 || $level > 255) {
            print &ui_print_error(L("ERR_APM_LEVEL_INVALID", $level));
        } else {
            if (disk_set_apm($disk_name, $level)) {
                print &ui_print_success(L("SUCCESS_DISK_APM_SET", $disk_name, $level));
            } else {
                print &ui_print_error(L("ERR_DISK_APM_SET_FAILED", $disk_name));
            }
        }
    }

    my $identify = $query ? disk_identify($query) : undef;
    my ($apm_supported, $apm_enabled, $apm_current) = (0, 0, '');
    if ($identify && $identify->{detail_map}) {
        my $apm_key = '';
        for my $k (keys %{ $identify->{detail_map} }) {
            if ($k =~ /advanced power management/) {
                $apm_key = $k;
                last;
            }
        }
        if ($apm_key) {
            my $apm_row = $identify->{detail_map}{$apm_key};
            $apm_supported = ($apm_row->{support} && $apm_row->{support} =~ /yes/i) ? 1 : 0;
            $apm_enabled = ($apm_row->{enabled} && $apm_row->{enabled} =~ /yes/i) ? 1 : 0;
            $apm_current = decode_raw_apmsetting($apm_row->{value} || '');
        }
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_DISK_POWER"));
    print &ui_form_start("disks.cgi", "post");
    print &ui_hidden("action", "advanced");

    my @power_heads = (
        L("COL_DISK"),
        L("COL_DISK_TYPE"),
        "Model / Hint",
        L("COL_POWER_STATUS"),
        L("COL_APM_STATUS"),
        L("COL_ACTIONS"),
    );
    my @power_data;
    my $dmesg_map = disk_dmesg_map($disks) || {};

    my %type_label = (
        hdd      => L("VALUE_TYPE_HDD"),
        ssd      => L("VALUE_TYPE_SSD"),
        memdisk  => L("VALUE_TYPE_MEMDISK"),
        usbstick => L("VALUE_TYPE_USB"),
        nvme     => "NVMe",
        disk     => "Disk",
        unknown  => L("VALUE_UNKNOWN"),
    );

    for my $disk (@$disks) {
        my $hint = $dmesg_map->{$disk} || '';
        my $dtype = disk_detect_type($disk, $hint);
        my $type_disp = $type_label{$dtype} || L("VALUE_UNKNOWN");
        my $pstate = disk_power_state($disk);
        # USB devices may report inaccurate CAM powermode states; avoid false "sleeping".
        if ($dtype eq 'usbstick' && $pstate eq 'sleeping') {
            $pstate = 'unknown';
        }
        my $spin_disp =
            $pstate eq 'ready'    ? L("VALUE_READY") :
            $pstate eq 'sleeping' ? L("VALUE_SLEEPING") :
                                    L("VALUE_UNKNOWN");
        my $apm_disp = L("VALUE_APM_UNKNOWN");
        if ($query && $disk eq $query) {
            if ($apm_supported) {
                $apm_disp = $apm_enabled ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
                $apm_disp .= " ($apm_current)" if $apm_current;
            } else {
                $apm_disp = L("VALUE_APM_UNSUPPORTED");
            }
        }
        my $disk_link = "<a href='disks.cgi?action=advanced&disk=" .
                        &url_encode($disk) . "'>" . &html_escape($disk) . "</a>";
        my $actions = join(' ',
            &ui_submit(L("BTN_SPINDOWN"), "spindown_$disk"),
            &ui_submit(L("BTN_SPINUP"), "spinup_$disk"),
        );
        push @power_data, [
            $disk_link,
            &html_escape($type_disp),
            &html_escape($hint || "-"),
            &html_escape($spin_disp),
            &html_escape($apm_disp),
            $actions,
        ];
    }
    print &ui_columns_table(\@power_heads, 100, \@power_data, undef, 1, undef, L("ERR_NO_DISKS_FOUND"));
    print &ui_form_end();

    if ($query) {
        my $query_hint = $dmesg_map->{$query} || '';
        my $query_type = disk_detect_type($query, $query_hint);
        my $is_usb_query = ($query_type && $query_type eq 'usbstick') ? 1 : 0;

        print &ui_hr();
        print &ui_subheading(L("SUB_DISK_APM"));
        if ($apm_supported) {
            my @apm_opts = (
                [ '255', L("OPT_APM_DISABLE") ],
                [ '1',   L("OPT_APM_MAX_SAVE_SPINDOWN") ],
                [ '32',  L("OPT_APM_HIGH_SAVE_SPINDOWN") ],
                [ '64',  L("OPT_APM_MED_SAVE_SPINDOWN") ],
                [ '96',  L("OPT_APM_LOW_SAVE_SPINDOWN") ],
                [ '127', L("OPT_APM_MIN_SAVE_SPINDOWN") ],
                [ '128', L("OPT_APM_MAX_SAVE") ],
                [ '254', L("OPT_APM_MAX_PERF") ],
            );
            print &ui_form_start("disks.cgi", "post");
            print &ui_hidden("action", "advanced");
            print &ui_hidden("apm_submit", 1);
            print &ui_hidden("apm_setting_disk", $query);
            print &ui_table_start(L("TABLE_DISK_APM"), "width=100%", 2);
            print &ui_table_row(L("ROW_APM_SUPPORTED"), L("VALUE_YES"));
            print &ui_table_row(L("ROW_APM_ENABLED"), $apm_enabled ? L("VALUE_YES") : L("VALUE_NO"));
            print &ui_table_row(L("ROW_APM_CURRENT"), $apm_current || L("VALUE_UNKNOWN"));
            print &ui_table_row(L("ROW_APM_NEW"), &ui_select("apm_newsetting", ($apm_current || '255'), \@apm_opts));
            print &ui_table_end();
            print &ui_form_end([ [ "apm_submit", L("BTN_SET_APM") ] ]);
        } else {
            if ($is_usb_query) {
                print &ui_alert("USB bridge/storage devices often do not expose ATA APM controls. This is expected for many USB devices.", "info");
            } else {
                print &ui_alert("APM is unsupported or not exposed by this disk/controller path on FreeBSD. This is common on many modern/enterprise drives and HBAs.", "info");
            }
        }

        print &ui_hr();
        print &ui_subheading(L("SUB_DISK_IDENTIFY", $query));
        if (!$identify || !@{ $identify->{main} || [] }) {
            if ($is_usb_query) {
                print &ui_alert("Detailed ATA identify data is usually unavailable behind USB bridge controllers. Model and basic status are shown above.", "info");
            } else {
                print &ui_alert("Detailed ATA identify data is unavailable through this controller path. Basic model and power status are still shown above.", "info");
            }
        } else {
            print &ui_table_start(L("TABLE_DISK_IDENTIFY"), "width=100%", 2);
            for my $row (@{ $identify->{main} }) {
                print &ui_table_row(
                    &html_escape($row->{property} || '-'),
                    &html_escape($row->{value} || '-')
                );
            }
            print &ui_table_end();
        }

        if ($identify && @{ $identify->{detail} || [] }) {
            print &ui_hr();
            print &ui_subheading(L("SUB_DISK_CAPABILITIES", $query));
            my @cap_heads = (
                L("COL_FEATURE"),
                L("COL_SUPPORT"),
                L("COL_ENABLED"),
                L("COL_VALUE"),
                L("COL_VENDOR"),
            );
            my @cap_data;
            for my $row (@{ $identify->{detail} }) {
                push @cap_data, [
                    &html_escape($row->{feature} || '-'),
                    &html_escape($row->{support} || '-'),
                    &html_escape($row->{enabled} || '-'),
                    &html_escape($row->{value} || '-'),
                    &html_escape($row->{vendor} || '-'),
                ];
            }
            print &ui_columns_table(\@cap_heads, 100, \@cap_data, undef, 1, undef, L("VALUE_NONE"));
        }
    } else {
        print "<p>" . L("MSG_DISK_QUERY_HINT") . "</p>";
    }

    print &ui_hr();
    print &ui_alert(L("MSG_ADVANCED_USE_MODIFY"), "info");
}

sub format_bytes {
    my ($bytes) = @_;
    my @units = qw(B KB MB GB TB);
    my $size = $bytes;
    my $unit_idx = 0;
    
    while ($size >= 1024 && $unit_idx < @units - 1) {
        $size /= 1024;
        $unit_idx++;
    }
    
    return sprintf("%.2f %s", $size, $units[$unit_idx]);
}

sub parse_size_bytes {
    my ($val) = @_;
    return undef unless defined $val && length $val;
    $val =~ s/^\s+|\s+$//g;
    if ($val =~ /^\d+$/) {
        return $val + 0;
    }
    if ($val =~ /^(\d+(?:\.\d+)?)([KMGTP])([iI]?)B?$/i) {
        my ($num, $unit) = ($1, uc($2));
        my %pow = (K => 1, M => 2, G => 3, T => 4, P => 5);
        my $base = 1024;
        return int($num * ($base ** $pow{$unit}));
    }
    return undef;
}

sub gpart_size_to_sectors {
    my ($val, $sector_size) = @_;
    return undef unless defined $val && length $val;
    $val =~ s/^\s+|\s+$//g;
    return undef unless length $val;
    $sector_size = 512 unless defined $sector_size && $sector_size =~ /^\d+$/ && $sector_size > 0;
    if ($val =~ /^\d+$/) {
        # gpart interprets bare integers as sectors, not bytes.
        return int($val);
    }
    my $bytes = parse_size_bytes($val);
    return undef unless defined $bytes;
    return int(($bytes + $sector_size - 1) / $sector_size);
}

sub is_gpart_size {
    my ($val) = @_;
    return 0 unless defined $val && length $val;
    $val =~ s/^\s+|\s+$//g;
    return 1 if $val =~ /^\d+$/;
    return 1 if $val =~ /^\d+(?:\.\d+)?[KMGTP]$/i;
    return 0;
}

sub decode_raw_apmsetting {
    my ($rawapm) = @_;
    return '' unless defined $rawapm && length $rawapm;
    if ($rawapm =~ /^0x[0-9a-fA-F]+$/) {
        return hex($rawapm);
    }
    if ($rawapm =~ /\/0x80([0-9a-fA-F]+)/) {
        return hex($1);
    }
    if ($rawapm =~ /\/0x([0-9a-fA-F]+)/) {
        return hex($1);
    }
    return '';
}

sub start_wipe_job {
    my (%opt) = @_;
    my $mode = $opt{mode} || 'zero';
    my $dev = $opt{device} || '';
    my $quick = $opt{quick} ? 1 : 0;
    my $quick_mib = $opt{quick_mib} || 16;

    my %valid = map { $_ => 1 } qw(zero random secure ata discard);
    return (0, undef, undef, "invalid wipe mode") unless $valid{$mode};
    return (0, undef, undef, "invalid wipe device") unless defined $dev && $dev =~ m{^/dev/};
    if (($mode eq 'secure' || $mode eq 'ata') && $dev !~ m{^/dev/[^/]+$}) {
        return (0, undef, undef, "secure erase requires a whole-disk target");
    }
    if (($mode eq 'secure' || $mode eq 'ata') && $dev =~ m{^/dev/[^/]+(?:p|s)\d+$}) {
        return (0, undef, undef, "secure erase requires a whole-disk target");
    }
    if ($quick && ($quick_mib !~ /^\d+$/ || $quick_mib < 1 || $quick_mib > 1048576)) {
        return (0, undef, undef, "invalid quick wipe size");
    }

    my $desc = $quick ? "quick-zero (${quick_mib}MiB)" : $mode;
    my $title = "wipe $desc: $dev";

    my $run = sub {
        print "Device: $dev\n";
        print "Mode: " . ($quick ? "quick-zero (${quick_mib} MiB)\n" : "$mode\n");
        print "\n";

        if ($quick) {
            my ($ok, $err) = disk_wipe_head($dev, $quick_mib);
            die $err unless $ok;
            return;
        }

        if ($mode eq 'zero') {
            my ($ok, $err) = disk_zero_write($dev);
            die $err unless $ok;
        } elsif ($mode eq 'random') {
            my ($ok, $err) = disk_random_write($dev);
            die $err unless $ok;
        } elsif ($mode eq 'secure') {
            my ($ok, $err) = disk_secure_erase($dev);
            die $err unless $ok;
        } elsif ($mode eq 'ata') {
            my ($ok, $err) = disk_ata_secure_erase($dev);
            die $err unless $ok;
        } elsif ($mode eq 'discard') {
            my ($ok, $err) = disk_blkdiscard($dev);
            die $err unless $ok;
        } else {
            die "unknown mode";
        }
    };

    return zfsguru_start_job(
        prefix => 'wipe',
        title  => $title,
        run    => $run,
    );
}

sub list_wipe_jobs {
    my (%opt) = @_;
    my $rows = zfsguru_list_jobs(prefix => 'wipe', %opt) || [];
    for my $j (@$rows) {
        next unless ref($j) eq 'HASH';
        my $s = $j->{status} // '';
        if ($s eq 'ok') {
            $j->{status} = L("VALUE_JOB_DONE");
        } elsif ($s eq 'failed') {
            $j->{status} = L("VALUE_JOB_FAILED");
        } elsif ($s eq 'killed') {
            $j->{status} = L("VALUE_JOB_KILLED");
        } else {
            $j->{status} = L("VALUE_JOB_RUNNING");
        }
    }
    return $rows;
}

sub normalize_label_value {
    my ($v) = @_;
    return '' if !defined($v);
    $v =~ s/^\s+|\s+$//g;
    return '' if $v =~ /^(?:\(null\)|null)$/i;
    return $v;
}

sub segment_device_basename {
    my ($seg) = @_;
    return '' unless $seg && ref($seg) eq 'HASH';
    if (defined($seg->{name}) && $seg->{name} ne '') {
        return $seg->{name};
    }
    my $dev = $seg->{dev} || '';
    return '' unless $dev;
    if ($dev =~ m{/([^/]+)$}) {
        return $1;
    }
    return $dev;
}

sub detect_partition_alignment {
    my ($seg, $sector_size) = @_;
    $sector_size = 512 unless defined($sector_size) && $sector_size =~ /^\d+$/ && $sector_size > 0;
    return (1, 'SECT') unless $seg && defined($seg->{start}) && $seg->{start} =~ /^\d+$/;
    my $start = int($seg->{start});
    return (1, 'SECT') if $start <= 0;
    my $offset = $start * $sector_size;
    my @candidates = (
        [ '4M',   4 * 1024 * 1024 ],
        [ '2M',   2 * 1024 * 1024 ],
        [ '1M',   1 * 1024 * 1024 ],
        [ '512K', 512 * 1024 ],
        [ '256K', 256 * 1024 ],
        [ '128K', 128 * 1024 ],
        [ '64K',  64  * 1024 ],
        [ '32K',  32  * 1024 ],
        [ '16K',  16  * 1024 ],
        [ '8K',   8   * 1024 ],
        [ '4K',   4   * 1024 ],
    );
    for my $c (@candidates) {
        my ($label, $bytes) = @$c;
        next unless $bytes > 0;
        next unless ($bytes % $sector_size) == 0;
        if (($offset % $bytes) == 0) {
            return (int($bytes / $sector_size), $label);
        }
    }
    return (1, 'SECT');
}

sub action_wipe_log {
    my $job = $in{'job'} || '';
    if ($job !~ /^wipe_[A-Za-z0-9_\-\.]+\.log$/) {
        print &ui_print_error(L("ERR_WIPE_LOG_INVALID"));
        return;
    }
    action_job_log();
}

sub action_job_log {
    my $job = $in{'job'} || '';
    my $disk_name = $in{'disk'} || '';
    if ($job !~ /^[A-Za-z0-9_\-\.]+\.log$/) {
        print &ui_print_error(L("ERR_WIPE_LOG_INVALID"));
        return;
    }
    my $txt = zfsguru_read_job_log(file => $job);
    if (!length $txt) {
        print &ui_print_error(L("ERR_WIPE_LOG_NOT_FOUND"));
        return;
    }
    print &ui_subheading(L("SUB_BG_JOB_LOG", $job));
    print "<pre>" . &html_escape($txt || '') . "</pre>";
    my $back = $disk_name && is_disk_name($disk_name)
        ? "disks.cgi?action=query&disk=" . &url_encode($disk_name)
        : "disks.cgi?action=list";
    print "<p><a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" . &html_escape($back) . "'>" . &html_escape(L("BTN_BACK")) . "</a></p>";
}
1;
