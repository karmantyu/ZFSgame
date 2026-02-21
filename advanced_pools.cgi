#!/usr/bin/env perl

package main;

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
require 'ui-lib.pl';

# ui-lib.pl provides the necessary UI helpers; nothing to alias here.
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();

# Parse CGI params
zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => "TITLE_ADV_POOLS");

# Ensure root privileges
eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('pools'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'pools'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'list';
$action = '' unless defined $action;
$action =~ s/\0.*$//s;
$action =~ s/[&;].*$//;
$action =~ s/^\s+|\s+$//g;
$action = 'list' if $action eq '';
my $pool   = $in{'pool'} || '';

# Navigation tabs
my %actions = (
    'list'     => 'List Pools',
    'view'     => 'View Pool Details',
    'clear'    => 'Clear Pool Errors',
    'create'   => 'Create Pool',
    'add_vdev' => 'Add Storage',
    'replace'  => 'Replace Device',
    'scrub'    => 'Manage Scrub',
    'import'   => 'Import Pool',
    'export'   => 'Export Pool',
    'destroy'  => 'Destroy Pool',
    'props'    => 'Properties',
    'history'  => 'History',
);

# Plain anchor tabs for reliable switching (works with &ReadParse)
my @tabs_list = (
    [ 'list', 'TAB_POOLS' ],
    [ 'create', 'TAB_CREATE' ],
    [ 'import', 'TAB_IMPORT' ],
    [ 'destroy', 'TAB_DESTROY' ],
);
push @tabs_list, [ 'benchmark', 'TAB_BENCHMARK' ] if cfg_bool('enable_benchmarking', 0);

print zfsguru_print_tabs(
    script => 'advanced_pools.cgi',
    active => $action,
    tabs   => \@tabs_list,
);

if ($action eq 'list' || !$action) {
    &action_list();
} elsif ($action eq 'view') {
    &action_view();
} elsif ($action eq 'clear') {
    &action_clear();
} elsif ($action eq 'create') {
    &action_create();
} elsif ($action eq 'add_vdev') {
    &action_add_vdev();
} elsif ($action eq 'replace') {
    &action_replace();
} elsif ($action eq 'scrub') {
    &action_scrub();
} elsif ($action eq 'import') {
    &action_import();
} elsif ($action eq 'export') {
    &action_export();
} elsif ($action eq 'destroy') {
    &action_destroy();
} elsif ($action eq 'rename') {
    &action_rename();
} elsif ($action eq 'upgrade') {
    &action_upgrade();
} elsif ($action eq 'bootfs') {
    &action_bootfs();
} elsif ($action eq 'cache') {
    &action_cache();
} elsif ($action eq 'slog') {
    &action_slog();
} elsif ($action eq 'spare') {
    &action_spare();
} elsif ($action eq 'props') {
    &action_properties();
} elsif ($action eq 'history') {
    &action_history();
} elsif ($action eq 'benchmark') {
    &action_benchmark();
} else {
    &action_list();
}

my $back_url = 'index.cgi';
if ($action ne 'list') {
    $back_url = 'advanced_pools.cgi?action=list';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

# Action handlers

sub cfg_bool {
    my ($key, $default) = @_;
    my $v = $zfsguru_lib::config{$key};
    return $default if !defined $v;
    return 1 if $v =~ /^(?:1|yes|true|on)$/i;
    return 0 if $v =~ /^(?:0|no|false|off)$/i;
    return $default;
}

sub detect_default_pool_version {
    my $zpool_cmd = $zfsguru_lib::config{'zpool_cmd'} || '/sbin/zpool';
    my ($rc, $out, $err) = run_cmd($zpool_cmd, 'upgrade', '-v');
    return '' if $rc != 0 || !defined $out || $out !~ /\S/;

    my $maxver = '';
    for my $line (split /\n/, $out) {
        if ($line =~ /^\s*(\d+)\s+/) {
            $maxver = $1 if $maxver eq '' || $1 > $maxver;
        }
    }
    return $maxver;
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

sub print_pool_action_help {
    my (%o) = @_;
    my $what = $o{what} || '';
    my $benefit = $o{benefit} || '';
    my $risk = $o{risk} || '';
    print "<div class='zfsguru-warn-block'>";
    print "<b>What it does:</b> " . &html_escape($what) . "<br>";
    print "<b>Benefit:</b> " . &html_escape($benefit) . "<br>";
    print "<b>Risk:</b> " . &html_escape($risk);
    print "</div>";
}

sub selected_vdevs_from_form {
    my @vdevs;
    my %seen;

    for my $key (sort keys %in) {
        next unless $key =~ /^disk_(.+)$/;
        next unless $in{$key};
        my $raw = $1;

        # Normalize and validate as a /dev path (allows e.g. da0p2, gpt/NAME, /dev/da0).
        my $dev = zfsguru_lib::_normalize_dev_path($raw);
        next unless $dev;
        next if $seen{$dev}++;
        push @vdevs, $dev;
    }

    return @vdevs;
}

sub vdev_type_min_disks {
    my ($vdev_type) = @_;
    return 1 if !defined $vdev_type || $vdev_type eq '' || $vdev_type eq 'stripe';
    return 2 if $vdev_type eq 'mirror';
    return 3 if $vdev_type eq 'raidz';
    return 4 if $vdev_type eq 'raidz2';
    return 5 if $vdev_type eq 'raidz3';
    return 1;
}

sub action_list {
    my $pools = zpool_list();

    my @heads = (
        L("COL_POOL"),
        L("COL_SIZE"),
        L("COL_ALLOCATED"),
        L("COL_FREE"),
        L("COL_CAPACITY"),
        L("COL_STATUS"),
        L("COL_ACTIONS"),
    );

    my @data;
    for my $p (@$pools) {
        my $pool_name = $p->{name};
        next unless defined $pool_name && length $pool_name;

        my $pool_url = "advanced_pools.cgi?action=view&pool=" . &url_encode($pool_name);
        my $pool_link = "<span style='white-space:nowrap !important; word-break:keep-all !important; overflow-wrap:normal !important; display:inline-block;'>" .
            "<a class='zfsguru-link zfsguru-pool-nowrap' style='white-space:nowrap !important; word-break:keep-all !important; overflow-wrap:normal !important; display:inline-block;' href='" .
            &html_escape($pool_url) . "' title='" . &html_escape($pool_name) . "'>" .
            &html_escape($pool_name) . "</a></span>";

        my $health = defined $p->{health} ? $p->{health} : '';
        my ($needs_attention, $attention_msg) = pool_needs_attention($pool_name, $health);
        my ($status_cls, $status_html);
        if ($needs_attention && $health eq 'ONLINE') {
            $status_cls = 'zfsguru-status-warn';
            my $safe_msg = &html_escape($attention_msg || '');
            my $title_attr = $safe_msg ne '' ? " title='$safe_msg'" : '';
            $status_html = "<span class='$status_cls zfsguru-status-badge'$title_attr>" .
                           &html_escape($health) .
                           "<br><span class='zfsguru-status-note' style='white-space:nowrap !important;word-break:normal !important;overflow-wrap:normal !important;text-transform:none !important;display:inline-block'>Action required!</span></span>";
        } else {
            $status_cls =
                $health eq 'ONLINE' ? 'zfsguru-status-ok' :
                $health ? 'zfsguru-status-bad' : 'zfsguru-status-unknown';
            $status_html = "<span class='$status_cls'>" . &html_escape($health || L("VALUE_UNKNOWN")) . "</span>";
        }

        my @btns = (
            &ui_link_icon($pool_url, L("BTN_DETAILS"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=props&pool=" . &url_encode($pool_name), L("BTN_PROPERTIES"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=history&pool=" . &url_encode($pool_name), L("BTN_HISTORY"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=scrub&pool=" . &url_encode($pool_name), L("BTN_SCRUB"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=add_vdev&pool=" . &url_encode($pool_name), L("BTN_ADD_STORAGE"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=replace&pool=" . &url_encode($pool_name), L("BTN_REPLACE_DEVICE"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=rename&pool=" . &url_encode($pool_name), L("BTN_RENAME_POOL"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=upgrade&pool=" . &url_encode($pool_name), L("BTN_UPGRADE_POOL"), undef, { class => 'warning' }),
            &ui_link_icon("advanced_pools.cgi?action=bootfs&pool=" . &url_encode($pool_name), L("BTN_SET_BOOTFS"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=cache&pool=" . &url_encode($pool_name), L("BTN_CACHE_DEVICES"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=slog&pool=" . &url_encode($pool_name), L("BTN_SLOG_DEVICES"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=spare&pool=" . &url_encode($pool_name), L("BTN_SPARE_DEVICES"), undef, { class => 'default' }),
            &ui_link_icon("advanced_pools.cgi?action=export&pool=" . &url_encode($pool_name), L("BTN_EXPORT_POOL"), undef, { class => 'warning' }),
            &ui_link_icon("advanced_pools.cgi?action=destroy&pool=" . &url_encode($pool_name), L("BTN_DESTROY_POOL"), undef, { class => 'danger' }),
        );
        my $actions_html = "<div class='zfsguru-actionlinks'>" . join(" ", @btns) . "</div>";

        push @data, [
            $pool_link,
            &html_escape($p->{size}  // ''),
            &html_escape($p->{alloc} // ''),
            &html_escape($p->{free}  // ''),
            &html_escape($p->{cap}   // ''),
            $status_html,
            $actions_html,
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_POOLS"), L("ERR_NO_POOLS_READABLE"));
}

sub action_benchmark {
    if (!cfg_bool('enable_benchmarking', 0)) {
        print &ui_print_error(L("ERR_BENCHMARKING_DISABLED"));
        return;
    }

    my $xnav_q = '';
    my $xnav_h = '';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        my $xv = $in{'xnavigation'};
        $xnav_q = "&xnavigation=$xv";
        $xnav_h = &ui_hidden("xnavigation", $xv);
    }

    my $bench_do = $in{'bench_do'} || '';
    if ($bench_do eq 'job_log') {
        my $job = $in{'job'} || '';
        if ($job !~ /^poolbench_[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_POOL_BENCH_LOG_INVALID"));
            return;
        }
        my $txt = zfsguru_read_job_log(file => $job);
        if (!length $txt) {
            print &ui_print_error(L("ERR_POOL_BENCH_LOG_NOT_FOUND"));
            return;
        }
        print &ui_subheading(L("SUB_POOL_BENCH_LOG", $job));
        print "<pre>" . &html_escape($txt || '') . "</pre>";
        print "<p><a class='button' href='advanced_pools.cgi?action=benchmark$xnav_q'>" . L("BTN_BACK") . "</a></p>";
        return;
    }
    if ($bench_do eq 'job_results') {
        my $job = $in{'job'} || '';
        if ($job !~ /^poolbench_[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_POOL_BENCH_LOG_INVALID"));
            return;
        }
        my $txt = zfsguru_read_job_log(file => $job);
        if (!length $txt) {
            print &ui_print_error(L("ERR_POOL_BENCH_LOG_NOT_FOUND"));
            return;
        }
        my ($rows, $meta) = parse_pool_benchmark_results($txt);
        print &ui_subheading(L("SUB_POOL_BENCH_RESULTS", $job));
        if (!$rows || !@$rows) {
            print &ui_print_error(L("ERR_POOL_BENCH_RESULTS_NOT_FOUND"));
        } else {
            print "<p>" . L("MSG_POOL_BENCH_RESULTS_NOTE") . "</p>";
            if (ref($meta) eq 'HASH' && defined $meta->{test_size} && $meta->{test_size} ne '') {
                print "<p><b>" . &html_escape(L("ROW_TEST_SIZE")) . ":</b> " . &html_escape($meta->{test_size}) . "</p>";
            }
            if (ref($meta) eq 'HASH' && ref($meta->{selected_tests}) eq 'ARRAY' && @{$meta->{selected_tests}}) {
                print "<p><b>" . &html_escape(L("ROW_BENCHMARK_SELECT")) . ":</b> "
                    . &html_escape(join(", ", @{$meta->{selected_tests}})) . "</p>";
            }
            print render_pool_benchmark_chart($rows);
        }
        my $log_link = "advanced_pools.cgi?action=benchmark&bench_do=job_log&job=" . &url_encode($job) . $xnav_q;
        print "<p>";
        print &ui_link_icon($log_link, L("BTN_VIEW_LOG"), undef, { class => 'primary' });
        print " ";
        print "<a class='button' href='advanced_pools.cgi?action=benchmark$xnav_q'>" . L("BTN_BACK") . "</a>";
        print "</p>";
        return;
    }

    if ($in{'kill_bg_job'}) {
        my $job = $in{'kill_bg_job'} || '';
        if ($job !~ /^poolbench_[A-Za-z0-9_.\-]+\.log$/) {
            print &ui_print_error(L("ERR_POOL_BENCH_LOG_INVALID"));
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
        my ($ok, $err, $count) = zfsguru_clear_job_logs(prefix => 'poolbench');
        if ($ok) {
            print &ui_print_success(L("SUCCESS_BG_LOGS_CLEARED", $count));
        } else {
            print &ui_print_error(L("ERR_BG_LOGS_CLEAR_FAILED", $err || 'clear failed'));
        }
    }

    if ($in{'start_benchmark'}) {
        my $pool_name = $in{'pool_select'} || $in{'pool'} || '';
        if (!$pool_name || !is_pool_name($pool_name)) {
            print &ui_print_error(L("ERR_POOL_BENCH_SELECT_POOL"));
            return;
        }

        my $size_mib = $in{'bench_size'} // '';
        $size_mib =~ s/^\s+|\s+$//g;
        if (!$size_mib || $size_mib !~ /^\d+$/ || $size_mib < 1) {
            print &ui_print_error(L("ERR_POOL_BENCH_INVALID_SIZE"));
            return;
        }

        my %tests = (
            normal    => $in{'bench_normal'} ? 1 : 0,
            lzjb      => $in{'bench_lzjb'} ? 1 : 0,
            gzip      => $in{'bench_gzip'} ? 1 : 0,
            bandwidth => $in{'bench_bandwidth'} ? 1 : 0,
        );
        my $any = 0;
        $any ||= $tests{$_} for keys %tests;
        if (!$any) {
            print &ui_print_error(L("ERR_POOL_BENCH_SELECT_TEST"));
            return;
        }

        if (!$in{'confirm_benchmark'}) {
            print &ui_alert(L("WARN_POOL_BENCHMARK"), 'warning');
            print &ui_print_error(L("ERR_POOL_BENCH_CONFIRM_REQUIRED"));
            return;
        }

        my $title = L("JOB_TITLE_POOL_BENCH", $pool_name);
        my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
            prefix => 'poolbench',
            title  => $title,
            run    => sub {
                pool_benchmark_job(
                    pool     => $pool_name,
                    size_mib => $size_mib,
                    tests    => \%tests,
                );
            },
            env    => { PAGER => 'cat' },
        );

        if (!$ok) {
            print &ui_print_error(L("ERR_POOL_BENCH_JOB_START_FAILED", $err));
        } else {
            my $link = "advanced_pools.cgi?action=benchmark&bench_do=job_log&job=" . &url_encode($log_file) . $xnav_q;
            print &ui_print_success(L("SUCCESS_POOL_BENCH_JOB_STARTED", $job_id));
            print "<p><a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" . &html_escape($link) . "'>"
                . &html_escape(L("BTN_VIEW_LOG")) . "</a></p>";
        }
    }

    print &ui_subheading(L("SUB_POOL_BENCHMARK"));
    print "<p>" . L("MSG_POOL_BENCHMARK_INTRO") . "</p>";
    print &ui_alert(L("WARN_POOL_BENCHMARK"), 'warning');

    my $pools = zpool_list();
    my @pool_opts = map { [ $_->{name}, $_->{name} ] } grep { $_->{name} } @{ $pools || [] };
    my $default_pool = $in{'pool_select'} || $in{'pool'} || ($pool_opts[0] ? $pool_opts[0][0] : '');

    my @size_opts = (
        [ 128,    "128 MiB" ],
        [ 512,    "512 MiB" ],
        [ 1024,   "1 GiB" ],
        [ 2048,   "2 GiB" ],
        [ 4096,   "4 GiB" ],
        [ 8192,   "8 GiB" ],
        [ 16384,  "16 GiB" ],
        [ 32768,  "32 GiB" ],
        [ 65536,  "64 GiB" ],
        [ 131072, "128 GiB" ],
        [ 262144, "256 GiB" ],
    );
    my $default_size = $in{'bench_size'};
    $default_size = 8192 if !defined $default_size || $default_size !~ /^\d+$/;

    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "benchmark");
    print $xnav_h if $xnav_h;
    print &ui_table_start(L("TABLE_POOL_BENCHMARK_CONFIG"), "width=100%", 2);
    print &ui_table_row(
        L("ROW_POOL"),
        &ui_select("pool_select", $default_pool, \@pool_opts)
    );
    print &ui_table_row(
        L("ROW_TEST_SIZE"),
        &ui_select("bench_size", $default_size, \@size_opts) . " <span class='zfsguru-muted'>" . L("MSG_POOL_BENCHMARK_SIZE_NOTE") . "</span>"
    );
    my $checks = join("<br>",
        &ui_checkbox("bench_normal", 1, L("OPT_POOL_BENCH_NORMAL"), ($in{'bench_normal'} || !$in{'start_benchmark'}) ? 1 : 0),
        &ui_checkbox("bench_lzjb", 1, L("OPT_POOL_BENCH_LZJB"), $in{'bench_lzjb'} ? 1 : 0),
        &ui_checkbox("bench_gzip", 1, L("OPT_POOL_BENCH_GZIP"), $in{'bench_gzip'} ? 1 : 0),
        &ui_checkbox("bench_bandwidth", 1, L("OPT_POOL_BENCH_BANDWIDTH"), ($in{'bench_bandwidth'} || !$in{'start_benchmark'}) ? 1 : 0),
    );
    print &ui_table_row(L("ROW_BENCHMARK_SELECT"), $checks);
    print &ui_table_row(
        L("ROW_CONFIRM"),
        &ui_checkbox("confirm_benchmark", 1, L("LBL_CONFIRM_POOL_BENCHMARK"), 0)
    );
    print &ui_table_end();
    print &ui_form_end([ [ "start_benchmark", L("BTN_RUN_BENCHMARK") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_POOL_BENCHMARK_JOBS"));
    print "<p>" . L("MSG_POOL_BENCHMARK_JOBS") . "</p>";
    my $jobs = zfsguru_list_jobs(prefix => 'poolbench');
    my @heads = (L("COL_JOB"), L("COL_STATUS"), L("COL_UPDATED"), L("COL_ACTIONS"));
    my @data;
    for my $j (@{ $jobs || [] }) {
        my $f = $j->{file} || next;
        my $raw_st = $j->{status} || '';
        my $view = "advanced_pools.cgi?action=benchmark&bench_do=job_log&job=" . &url_encode($f) . $xnav_q;
        my $view_btn = &ui_link_icon($view, L("BTN_VIEW_LOG"), undef, { class => 'primary' });
        my $results_btn = '';
        if ($raw_st eq 'ok') {
            my $results = "advanced_pools.cgi?action=benchmark&bench_do=job_results&job=" . &url_encode($f) . $xnav_q;
            $results_btn = " " . &ui_link_icon($results, L("BTN_VIEW_RESULTS"), undef, { class => 'success' });
        }
        my $kill_btn = '';
        if ($raw_st eq 'running') {
            $kill_btn = "<form method='post' action='advanced_pools.cgi' style='display:inline;margin-left:6px'>"
                      . &ui_hidden("action", "benchmark")
                      . ($xnav_h ? $xnav_h : '')
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
            &html_escape($raw_st),
            &html_escape($j->{mtime} || ''),
            $view_btn . $results_btn . $kill_btn,
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_POOL_BENCHMARK_JOBS"), L("VALUE_NONE"));
    print "<p>";
    print &ui_link_icon("advanced_pools.cgi?action=benchmark$xnav_q", L("BTN_REFRESH"), undef, { class => 'primary' });
    print " ";
    print &ui_form_start("advanced_pools.cgi", "post", "style='display:inline'");
    print &ui_hidden("action", "benchmark");
    print $xnav_h if $xnav_h;
    print &ui_form_end([
        [ "clear_bg_logs", L("BTN_EMPTY_LOGS"), undef, 0, "style='background:#d9534f;color:#fff;border-color:#d9534f'" ],
    ]);
    print "</p>";
}

sub action_view {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);
    
    my $status = zpool_status($pool_name);
    if (!defined $status) {
        print &ui_print_error(L("ERR_POOL_STATUS_FAILED"));
        return;
    }
    
    print &ui_subheading(L("SUB_POOL", $pool_name));
    print_pool_action_help(
        what    => "Shows live zpool status details for this pool.",
        benefit => "Fast health and topology diagnostics.",
        risk    => "Read-only view; no direct risk."
    );

    my $pool_state = '';
    if ($status =~ /^\s*state:\s*(\S+)/m) {
        $pool_state = uc($1);
    }
    my ($show_issue_actions, undef) = pool_needs_attention($pool_name, $pool_state);
    if ($show_issue_actions) {
        my $pool_q = &url_encode($pool_name);
        print "<p>";
        print &ui_link_icon("advanced_pools.cgi?action=clear&pool=$pool_q", L("BTN_ZPOOL_CLEAR"), undef, { class => 'warning' });
        print " ";
        print &ui_link_icon("advanced_pools.cgi?action=replace&pool=$pool_q", L("BTN_REPLACE_DEVICE"), undef, { class => 'danger' });
        print "</p>";
    }

    print "<pre>" . &html_escape($status) . "</pre>";
}

sub action_clear {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);

    if ($in{'do_clear'}) {
        eval {
            must_run(($zfsguru_lib::ZPOOL || '/sbin/zpool'), 'clear', $pool_name);
            log_info("Cleared zpool errors for $pool_name");
            print &ui_print_success(L("SUCCESS_POOL_CLEARED", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_POOL_CLEAR_FAILED", $@));
        }
        return;
    }

    print &ui_subheading(L("SUB_POOL_CLEAR", $pool_name));
    print_pool_action_help(
        what    => "Runs zpool clear to reset current error counters on the pool.",
        benefit => "Useful after correcting the root issue to clear stale error state.",
        risk    => "This does not repair data; it only clears current pool error status."
    );

    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "clear");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("do_clear", 1);
    print "<p>";
    print &ui_submit(L("BTN_ZPOOL_CLEAR"), "do_clear", 0, "style='background:#f0ad4e;color:#fff;border-color:#eea236'");
    print " ";
    print &ui_link("advanced_pools.cgi?action=view&pool=" . &url_encode($pool_name), L("BTN_CANCEL"));
    print "</p>";
    print &ui_form_end();
}

sub action_create {
    if ($in{'create_pool'} || $in{'confirm_create'}) {
        my $pool_name = $in{'pool_name'} // '';
        my $vdev_type = $in{'vdev_type'} || 'stripe';
        my $trim = sub {
            my ($v) = @_;
            $v = '' unless defined $v;
            $v =~ s/^\s+|\s+$//g;
            return $v;
        };
        my $pick_whitelist = sub {
            my ($prop, $value, $allowed_ref) = @_;
            $value = $trim->($value);
            return '' if $value eq '';
            my %ok = map { $_ => 1 } @$allowed_ref;
            if (!$ok{$value}) {
                print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", $prop, $value));
                return undef;
            }
            return $value;
        };

        if (!is_pool_name($pool_name)) {
            print &ui_print_error(L("ERR_INVALID_POOL_NAME", $pool_name));
            return;
        }

        my %valid_vdev_type = map { $_ => 1 } qw(stripe mirror raidz raidz2 raidz3);
        if (!$valid_vdev_type{$vdev_type}) {
            print &ui_print_error(L("ERR_INVALID_VDEV_TYPE"));
            return;
        }
        my %create_opt = (
            ashift         => $trim->($in{'ashift'}),
            pool_version   => $trim->($in{'pool_version'}),
            recordsize     => $trim->($in{'recordsize'}),
            compression    => $trim->($in{'compression'}),
            atime          => $trim->($in{'atime'}),
            mountpoint     => $trim->($in{'mountpoint'}),
            prop_sync      => $trim->($in{'prop_sync'}),
            prop_exec      => $trim->($in{'prop_exec'}),
            prop_canmount  => $trim->($in{'prop_canmount'}),
            prop_acltype   => $trim->($in{'prop_acltype'}),
            prop_aclinherit=> $trim->($in{'prop_aclinherit'}),
            prop_aclmode   => $trim->($in{'prop_aclmode'}),
            prop_xattr     => $trim->($in{'prop_xattr'}),
            force_create   => ($in{'force_create'} ? 1 : 0),
            acl_inherit_fd => ($in{'acl_inherit_fd'} ? 1 : 0),
        );

        if ($create_opt{ashift} ne '' && ($create_opt{ashift} !~ /^\d+$/ || $create_opt{ashift} < 9 || $create_opt{ashift} > 16)) {
            print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", 'ashift', $create_opt{ashift}));
            return;
        }
        if ($create_opt{pool_version} ne '' && $create_opt{pool_version} !~ /^\d+$/) {
            print &ui_print_error(L("ERR_INVALID_PROPERTY_VALUE", 'version', $create_opt{pool_version}));
            return;
        }
        if ($create_opt{mountpoint} ne '' && !is_mountpoint($create_opt{mountpoint})) {
            print &ui_print_error(L("ERR_MOUNTPOINT_INVALID", $create_opt{mountpoint}));
            return;
        }
        $create_opt{recordsize} = $pick_whitelist->('recordsize', $create_opt{recordsize}, [qw(512 1K 2K 4K 8K 16K 32K 64K 128K 256K 512K 1M 2M 4M)]);
        return unless defined $create_opt{recordsize};
        $create_opt{compression} = $pick_whitelist->('compression', $create_opt{compression}, [qw(lz4 zstd-1 zstd zstd-6 zstd-9 zstd-19 off)]);
        return unless defined $create_opt{compression};
        $create_opt{atime} = $pick_whitelist->('atime', $create_opt{atime}, [qw(on off)]);
        return unless defined $create_opt{atime};
        $create_opt{prop_sync} = $pick_whitelist->('sync', $create_opt{prop_sync}, [qw(standard always disabled)]);
        return unless defined $create_opt{prop_sync};
        $create_opt{prop_exec} = $pick_whitelist->('exec', $create_opt{prop_exec}, [qw(on off)]);
        return unless defined $create_opt{prop_exec};
        $create_opt{prop_canmount} = $pick_whitelist->('canmount', $create_opt{prop_canmount}, [qw(on off)]);
        return unless defined $create_opt{prop_canmount};
        $create_opt{prop_acltype} = $pick_whitelist->('acltype', $create_opt{prop_acltype}, [qw(nfsv4 off posix)]);
        return unless defined $create_opt{prop_acltype};
        $create_opt{prop_aclinherit} = $pick_whitelist->('aclinherit', $create_opt{prop_aclinherit}, [qw(passthrough passthrough-x restricted noallow discard)]);
        return unless defined $create_opt{prop_aclinherit};
        $create_opt{prop_aclmode} = $pick_whitelist->('aclmode', $create_opt{prop_aclmode}, [qw(passthrough restricted groupmask discard)]);
        return unless defined $create_opt{prop_aclmode};
        $create_opt{prop_xattr} = $pick_whitelist->('xattr', $create_opt{prop_xattr}, [qw(sa on off)]);
        return unless defined $create_opt{prop_xattr};

        my @vdevs = selected_vdevs_from_form();
        
        if (!@vdevs) {
            print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            return;
        }

        my $min_disks = vdev_type_min_disks($vdev_type);
        if (scalar(@vdevs) < $min_disks) {
            print &ui_print_error(L("ERR_NOT_ENOUGH_DISKS_FOR_VDEV", $min_disks, uc($vdev_type)));
            return;
        }
        
        # Build vdev arguments
        my @vdev_args;
        if ($vdev_type eq 'mirror') {
            push @vdev_args, 'mirror', @vdevs;
        } elsif ($vdev_type eq 'raidz') {
            push @vdev_args, 'raidz', @vdevs;
        } elsif ($vdev_type eq 'raidz2') {
            push @vdev_args, 'raidz2', @vdevs;
        } elsif ($vdev_type eq 'raidz3') {
            push @vdev_args, 'raidz3', @vdevs;
        } else {
            @vdev_args = @vdevs; # stripe
        }
        
        # If confirm button clicked, execute the command
        if ($in{'confirm_create'}) {
            if (!$in{'confirm_understand_create'}) {
                print &ui_print_error(L("ERR_CONFIRM_CREATE_REQUIRED"));
                return;
            }

            # Safety check: block creating a pool from devices that are already in any zpool.
            my @conflicts;
            for my $dev (@vdevs) {
                my $pools = device_in_zpool($dev);
                if ($pools && @$pools) {
                    push @conflicts, "$dev (" . join(',', @$pools) . ")";
                }
            }
            if (@conflicts) {
                print &ui_print_error(L("ERR_VDEV_IN_POOL", join(', ', @conflicts)));
                return;
            }

            eval {
                my %pool_props = ();
                my %root_props = ();

                $pool_props{ashift}  = $create_opt{ashift} if $create_opt{ashift} ne '';
                $pool_props{version} = $create_opt{pool_version} if $create_opt{pool_version} ne '';

                for my $k (qw(recordsize compression atime acltype aclinherit aclmode xattr sync exec canmount mountpoint)) {
                    my $src_key = $k;
                    $src_key = "prop_$k" if $k =~ /^(?:acltype|aclinherit|aclmode|xattr|sync|exec|canmount)$/;
                    my $val = $create_opt{$src_key};
                    next unless defined $val && $val ne '';
                    $root_props{$k} = $val;
                }

                my @create_args;
                push @create_args, '-f' if $create_opt{force_create};
                for my $k (sort keys %pool_props) {
                    push @create_args, '-o', "$k=$pool_props{$k}";
                }
                for my $k (sort keys %root_props) {
                    push @create_args, '-O', "$k=$root_props{$k}";
                }

                my @cmd = (($zfsguru_lib::ZPOOL || '/sbin/zpool'), 'create', @create_args, $pool_name, @vdev_args);
                must_run(@cmd);
                if ($create_opt{acl_inherit_fd}) {
                    my ($ok_fd, $msg_fd) = apply_fd_acl_flags_for_dataset($pool_name);
                    if (!$ok_fd) {
                        log_warn("Pool created but ACL :fd flag apply skipped/failed for $pool_name: $msg_fd");
                    } else {
                        log_info("Applied ACL :fd inheritance flags for $pool_name");
                    }
                }
                log_info("Created pool $pool_name");
                print &ui_print_success(L("SUCCESS_POOL_CREATED", $pool_name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_POOL_CREATE_FAILED", $@));
            }
            return;
        }
        
        # Show confirmation with command preview
        print &ui_subheading(L("SUB_CONFIRM_POOL_CREATE"));
        print "<div class='zfsguru-code-block'>";
        print "<b>" . L("LBL_COMMAND_TO_EXECUTE") . "</b><br>";

        my %pool_props = ();
        my %root_props = ();

        $pool_props{ashift} = $create_opt{ashift} if $create_opt{ashift} ne '';
        $pool_props{version} = $create_opt{pool_version} if $create_opt{pool_version} ne '';

        for my $k (qw(recordsize compression atime acltype aclinherit aclmode xattr sync exec canmount mountpoint)) {
            my $src_key = $k;
            $src_key = "prop_$k" if $k =~ /^(?:acltype|aclinherit|aclmode|xattr|sync|exec|canmount)$/;
            my $val = $create_opt{$src_key};
            next unless defined $val && $val ne '';
            $root_props{$k} = $val;
        }

        my @cmd_preview = ('zpool', 'create');
        push @cmd_preview, '-f' if $create_opt{force_create};
        for my $k (sort keys %pool_props) {
            push @cmd_preview, '-o', "$k=$pool_props{$k}";
        }
        for my $k (sort keys %root_props) {
            push @cmd_preview, '-O', "$k=$root_props{$k}";
        }
        push @cmd_preview, $pool_name, @vdev_args;
        print &html_escape(join(' ', @cmd_preview));
        print "</div>";

        if (($create_opt{prop_sync} || '') eq 'disabled') {
            print &ui_alert(L("WARN_SYNC_DISABLED"), 'warning');
        }
        
        print "<b>" . L("LBL_CONFIGURATION") . "</b><br>";
        print "<ul>";
        print "<li>" . L("ROW_POOL_NAME") . ": <b>" . &html_escape($pool_name) . "</b></li>";
        print "<li>" . L("ROW_REDUNDANCY_TYPE") . ": <b>" . &html_escape(uc($vdev_type)) . "</b></li>";
        print "<li>" . L("ROW_DISKS") . ": <b>" . join(", ", map { &html_escape($_) } @vdevs) . "</b></li>";
        print "<li>" . L("ROW_ASHIFT") . ": <b>" . (($create_opt{ashift} ne '') ? &html_escape($create_opt{ashift}) : L("VALUE_AUTO")) . "</b></li>";
        print "<li>Pool Version: <b>" . (($create_opt{pool_version} ne '') ? &html_escape($create_opt{pool_version}) : L("VALUE_AUTO")) . "</b></li>";
        print "<li>" . L("ROW_RECORDSIZE") . ": <b>" . (($create_opt{recordsize} ne '') ? &html_escape($create_opt{recordsize}) : L("VALUE_RECORDSIZE_DEFAULT")) . "</b></li>";
        print "<li>" . L("ROW_COMPRESSION") . ": <b>" . (($create_opt{compression} ne '') ? &html_escape($create_opt{compression}) : L("VALUE_COMPRESSION_DEFAULT")) . "</b></li>";
        print "<li>" . L("ROW_ACCESS_TIME") . ": <b>" . (($create_opt{atime} ne '') ? &html_escape($create_opt{atime}) : L("VALUE_ATIME_DEFAULT")) . "</b></li>";
        print "<li>" . L("ROW_SYNC") . ": <b>" . (($create_opt{prop_sync} ne '') ? &html_escape($create_opt{prop_sync}) : L("VALUE_SYNC_DEFAULT")) . "</b></li>";
        print "<li>Exec: <b>" . (($create_opt{prop_exec} ne '') ? &html_escape($create_opt{prop_exec}) : L("VALUE_NONE")) . "</b></li>";
        print "<li>Canmount: <b>" . (($create_opt{prop_canmount} ne '') ? &html_escape($create_opt{prop_canmount}) : L("VALUE_NONE")) . "</b></li>";
        print "<li>" . L("ROW_MOUNTPOINT") . ": <b>" . (($create_opt{mountpoint} ne '') ? &html_escape($create_opt{mountpoint}) : L("VALUE_AUTO")) . "</b></li>";
        print "<li>ACL inherit flags (:fd): <b>" . ($create_opt{acl_inherit_fd} ? L("VALUE_YES") : L("VALUE_NO")) . "</b></li>";
        print "<li>Force Creation: <b>" . ($create_opt{force_create} ? L("VALUE_YES") : L("VALUE_NO")) . "</b></li>";
        my @acl_props;
        push @acl_props, "acltype=" . $create_opt{prop_acltype} if $create_opt{prop_acltype};
        push @acl_props, "aclinherit=" . $create_opt{prop_aclinherit} if $create_opt{prop_aclinherit};
        push @acl_props, "aclmode=" . $create_opt{prop_aclmode} if $create_opt{prop_aclmode};
        push @acl_props, "xattr=" . $create_opt{prop_xattr} if $create_opt{prop_xattr};
        print "<li>" . L("ROW_ACL_XATTR") . ": <b>" . (@acl_props ? &html_escape(join(", ", @acl_props)) : L("VALUE_NONE")) . "</b></li>";
        print "</ul>";
        
        print &ui_form_start("advanced_pools.cgi", "post");
        print &ui_hidden("action", "create");
        print &ui_hidden("pool_name", $pool_name);
        print &ui_hidden("vdev_type", $vdev_type);
        print &ui_hidden("ashift", $create_opt{ashift}) if $create_opt{ashift} ne '';
        print &ui_hidden("pool_version", $create_opt{pool_version}) if $create_opt{pool_version} ne '';
        print &ui_hidden("recordsize", $create_opt{recordsize}) if $create_opt{recordsize} ne '';
        print &ui_hidden("compression", $create_opt{compression}) if $create_opt{compression} ne '';
        print &ui_hidden("atime", $create_opt{atime}) if $create_opt{atime} ne '';
        print &ui_hidden("mountpoint", $create_opt{mountpoint}) if $create_opt{mountpoint} ne '';
        print &ui_hidden("force_create", 1) if $create_opt{force_create};
        print &ui_hidden("acl_inherit_fd", 1) if $create_opt{acl_inherit_fd};
        print &ui_hidden("prop_acltype", $create_opt{prop_acltype}) if $create_opt{prop_acltype} ne '';
        print &ui_hidden("prop_aclinherit", $create_opt{prop_aclinherit}) if $create_opt{prop_aclinherit} ne '';
        print &ui_hidden("prop_aclmode", $create_opt{prop_aclmode}) if $create_opt{prop_aclmode} ne '';
        print &ui_hidden("prop_xattr", $create_opt{prop_xattr}) if $create_opt{prop_xattr} ne '';
        print &ui_hidden("prop_sync", $create_opt{prop_sync}) if $create_opt{prop_sync} ne '';
        print &ui_hidden("prop_exec", $create_opt{prop_exec}) if $create_opt{prop_exec} ne '';
        print &ui_hidden("prop_canmount", $create_opt{prop_canmount}) if $create_opt{prop_canmount} ne '';
        foreach my $disk (@vdevs) {
            $disk =~ s/\/dev\///;
            print &ui_hidden("disk_$disk", 1);
        }

        print "<div class='zfsguru-margin-top'>";
        print &ui_checkbox("confirm_understand_create", 1, L("LBL_CONFIRM_UNDERSTAND_CREATE"), 0);
        print "</div>";

        # Rely on the Proceed submit button name to set the confirmation flag
        
        print "<div class='zfsguru-margin-top-lg'>";
        print &ui_submit(L("BTN_PROCEED_CREATE"), "confirm_create", 0,
            "style='background:#d9534f;color:#fff;border-color:#d43f3a;'") . " ";
        print &ui_submit(L("BTN_CANCEL"), "cancel_create");
        print "</div>";
        print &ui_form_end();
        return;
    }
    
    # Display create form
    print &ui_subheading(L("SUB_CREATE_POOL"));
    print_pool_action_help(
        what    => "Creates a new pool from selected disks/partitions.",
        benefit => "Lets you define redundancy and core defaults in one step.",
        risk    => "Wrong disk selection can overwrite existing data."
    );
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "create");
    print &ui_hidden("create_pool", 1);
    my $default_pool_version = detect_default_pool_version();
    my $pool_version_default = defined $in{'pool_version'} ? $in{'pool_version'} : $default_pool_version;
    
    print &ui_table_start(L("TABLE_POOL_CONFIG"), "width=100%", 2);
    print &ui_table_row(L("ROW_POOL_NAME"), &ui_textbox("pool_name", "", 20));
    print &ui_table_row(L("ROW_REDUNDANCY"), &ui_select("vdev_type", "", [
        [ "stripe", L("OPT_RAID0_STRIPE") ],
        [ "mirror", L("OPT_RAID1_MIRROR") ],
        [ "raidz", L("OPT_RAIDZ") ],
        [ "raidz2", L("OPT_RAIDZ2") ],
        [ "raidz3", L("OPT_RAIDZ3") ],
    ]));
    print &ui_table_row(L("ROW_ASHIFT"), &ui_textbox("ashift", "12", 5));
    print &ui_table_row("Pool Version", &ui_textbox("pool_version", $pool_version_default, 10) . " <small>(default pool version)</small>");
    print &ui_table_row(L("ROW_RECORDSIZE"), &ui_select("recordsize", "128K", [
        [ "512", "512B" ],
        [ "1K", "1K" ],
        [ "2K", "2K" ],
        [ "4K", "4K" ],
        [ "8K", "8K" ],
        [ "16K", "16K" ],
        [ "32K", "32K" ],
        [ "64K", "64K" ],
        [ "128K", "128K (General default)" ],
        [ "256K", "256K" ],
        [ "512K", "512K" ],
        [ "1M", "1M (Media/Large file default)" ],
        [ "2M", "2M" ],
        [ "4M", "4M" ],
    ]));
    print &ui_table_row(L("ROW_COMPRESSION"), &ui_select("compression", "lz4", [
        [ "lz4",    L("OPT_LZ4_FAST") ],
        [ "zstd-1", L("OPT_ZSTD1_FAST") ],
        [ "zstd",   L("OPT_ZSTD_DEFAULT") ],
        [ "zstd-6", L("OPT_ZSTD6_GOOD") ],
        [ "zstd-9", L("OPT_ZSTD9_HIGH") ],
        [ "zstd-19",L("OPT_ZSTD19_MAX") ],
        [ "off", "off" ],
    ]));
    print &ui_table_row(L("ROW_ATIME"), &ui_select("atime", "off", [
        [ "off", L("OPT_OFF_RECOMMENDED") ],
        [ "on", "on" ],
    ]));
    my $acltype_for_default = defined $in{'prop_acltype'} ? $in{'prop_acltype'} : 'nfsv4';
    my $acl_fd_default = defined $in{'acl_inherit_fd'}
        ? ($in{'acl_inherit_fd'} ? 1 : 0)
        : (lc($acltype_for_default) eq 'nfsv4' ? 1 : 0);
    print &ui_table_row(L("ROW_MOUNTPOINT"), &ui_filebox("mountpoint", ($in{'mountpoint'} // ''), 40, 0, undef, undef, 1) . " " . L("HINT_MOUNTPOINT_DEFAULT"));
    print &ui_table_row("ACL inherit flags", &ui_checkbox("acl_inherit_fd", 1, "Add :fd to base NFSv4 ACL entries", $acl_fd_default));
    print &ui_table_row("Force Creation", &ui_checkbox("force_create", 1, "Force use of disks, even if they are in use (-f)", 0));
    print &ui_table_row(L("ROW_SYNC_BEHAVIOR"), &ui_select("prop_sync", "standard", [
        [ "standard", "standard (default)" ],
        [ "always", "always" ],
        [ "disabled", "disabled (performance, data loss risk)" ],
    ]));
    print &ui_table_row("Exec", &ui_select("prop_exec", "on", [
        [ "on", "on (default)" ],
        [ "off", "off" ],
    ]));
    print &ui_table_row("Canmount", &ui_select("prop_canmount", "on", [
        [ "on", "on (default)" ],
        [ "off", "off" ],
    ]));

    my $adv_props_html =
        "ACL type: " . &ui_select("prop_acltype", "nfsv4", [
            [ "nfsv4", "nfsv4 (default)" ],
            [ "off", "off" ],
            [ "posix", "posix" ],
        ]) . "<br>" .
        "ACL inherit: " . &ui_select("prop_aclinherit", "passthrough", [
            [ "passthrough", "passthrough (default)" ],
            [ "passthrough-x", "passthrough-x (add :fd for inherited entries)" ],
            [ "restricted", "restricted" ],
            [ "noallow", "noallow" ],
            [ "discard", "discard" ],
        ]) . "<br>" .
        "ACL mode: " . &ui_select("prop_aclmode", "passthrough", [
            [ "passthrough", "passthrough (default)" ],
            [ "restricted", "restricted" ],
            [ "groupmask", "groupmask" ],
            [ "discard", "discard" ],
        ]) . "<br>" .
        "xattr: " . &ui_select("prop_xattr", "sa", [
            [ "sa", "sa (default)" ],
            [ "on", "on" ],
            [ "off", "off" ],
        ]);
    print &ui_table_row(L("ROW_ACL_ATTRIBUTES"), $adv_props_html . "<br><small>" . L("HINT_ACL_COMPAT") . "</small>");

    
    print &ui_table_end();
    print "<div class='ui_subheading'>" . L("ROW_SELECT_DISKS") . "</div>";
    # Build a structured device/partition map
    my $devdir = '/dev';
    my %glabel_map;
    if (open(my $gl, '-|', 'glabel status')) {
        while (my $line = <$gl>) {
            chomp $line;
            # allow leading whitespace in output lines
            if ($line =~ /^\s*(\S+)\s+\S+\s+(\S+)$/) {
                my ($label, $target) = ($1, $2);
                # normalize target (strip /dev/)
                (my $t = $target) =~ s{^/dev/}{};
                $glabel_map{$label} = $t;
                $glabel_map{lc $label} = $t;
                $glabel_map{$t} = $t;
                $glabel_map{"/dev/$t"} = $t;
            }
        }
        close($gl);
    }
    my %devs; # device => { scheme => '', parts => [ ... ] }
    my %boot_parts; # track which partitions are boot partitions
    if (opendir(my $dh, $devdir)) {
        my @all = readdir($dh);
        closedir($dh);
        foreach my $d (@all) {
            if ($d =~ /^(da|ada|sd|vd|nvme\d+n\d+|md)\d+$/) {
                # Whole disk
                my $scheme = '';
                if (open(my $gp, '-|', "gpart show $d 2>/dev/null")) {
                    while (my $l = <$gp>) {
                        if ($l =~ /GPT/) { $scheme = 'GPT'; last; }
                        if ($l =~ /MBR/) { $scheme = 'MBR'; last; }
                    }
                    close($gp);
                }
                $devs{$d} = { scheme => $scheme, parts => [] };
            }
        }
        # Now add partitions/slices to their parent disk and detect boot partitions
        # Use gpart show to get partition types
        foreach my $d (@all) {
            if ($d =~ /^(da|ada|sd|vd|nvme\d+n\d+|md)\d+$/) {
                # Get partition info for this disk with types
                if (open(my $gp, '-|', "gpart show $d 2>/dev/null")) {
                    while (my $line = <$gp>) {
                        # Parse partition lines: start size index type [flags] (size_human)
                        if ($line =~ /^\s+\d+\s+(\d+)\s+(\d+)\s+(\S+)/) {
                            my ($size_blocks, $idx, $ptype) = ($1, $2, $3);
                            next if $ptype eq '-' || $ptype eq 'free';
                            
                            # Check if this is a boot-type partition or a very small partition (likely boot)
                            # Boot types: freebsd-boot, efi, bios-boot, etc.
                            # Also mark as boot if size <= 1024 blocks (512K) and index is 1
                            if ($ptype =~ /\b(freebsd-boot|efi|bios-boot|netbsd-boot|openbsd-boot|apple-boot)\b/i 
                                || ($idx == 1 && $size_blocks <= 1024)) {
                                my $part_name = $d . 'p' . $idx;
                                $boot_parts{$part_name} = 1;
                            }
                        }
                    }
                    close($gp);
                }
            }
        }
        # Now add partitions to their parent disk structures
        foreach my $d (@all) {
            if ($d =~ /^((da|ada|sd|vd|nvme\d+n\d+|md)\d+)[ps](\d+)$/) {
                my ($parent, $part) = ($1, $d);
                if (exists $devs{$parent}) {
                    push @{ $devs{$parent}{parts} }, $part;
                }
            }
        }
    }

    # Render structured table: device | dynamic partition columns
    # Build pool membership map from zpool status (robust against label names)
    my $status_all = zpool_status();
    my %member_to_pool;
    my %used_map;
    my $pinfo = parse_zpool_status( defined($status_all) ? $status_all : '' );
    # Populate membership map from parsed zpool device names (with many common key variants)
    for my $p (@$pinfo) {
        my $poolname = $p->{name} || '';
        for my $d (@{ $p->{devices} || [] }) {
            my $orig = $d->{name} || '';
            next unless $orig;
            (my $n = $orig) =~ s{^/dev/}{};
            # add common variants for matching
            my @variants = ($n, "/dev/$n", lc($n));
            # if labelled like gpt/NAME, also map NAME and /dev/gpt/NAME
            if ($n =~ m{^(?:gpt/)?(.+)$}) {
                my $base = $1;
                push @variants, $base, "/dev/$base", "gpt/$base", "/dev/gpt/$base", lc($base), lc("gpt/$base");
            }
            # if label exists in glabel map also map its target
            if (exists $glabel_map{$n}) { push @variants, $glabel_map{$n}; }

            for my $v (@variants) {
                next unless defined $v && length $v;
                $member_to_pool{$v} = $poolname;
                $used_map{$v} = 1;
            }
        }
    }
    # Build authoritative mapping by parsing each pool's device section (correct per-pool assignment)
    my %pool_devices;
    if (defined $status_all && $status_all ne '') {
        my $current_pool;
        my $in_config = 0;
        foreach my $line (split(/\n/, $status_all)) {
            if ($line =~ /^\s*pool:\s+(\S+)/) {
                $current_pool = $1;
                $in_config = 0;
            } elsif ($line =~ /^\s*config:/) {
                $in_config = 1;
            } elsif ($in_config && $current_pool && $line =~ /^\s+(\S+)\s+(\S+)/) {
                # Device line: two tokens minimum (name and state like "gpt/SEA1  ONLINE" or "da2p2   ONLINE")
                my ($dev_id, $state) = ($1, $2);
                # Skip keywords and group names
                next if $dev_id =~ /^(?:mirror|raidz|logs|cache|spares)\d*-?/;
                next if $dev_id eq $current_pool;
                # Skip non-device keywords (scan, state, errors, etc.)
                next if $dev_id =~ /^(?:scan|state|errors|config|NAME):/;
                # This is a real device; add to mapping
                $pool_devices{$dev_id} = $current_pool;
                # Also add glabel target if it exists
                if (exists $glabel_map{$dev_id}) {
                    $pool_devices{$glabel_map{$dev_id}} = $current_pool;
                }
            }
        }
    }

    # Update member_to_pool with the authoritative per-pool mapping
    for my $dev (keys %pool_devices) {
        my $pool = $pool_devices{$dev};
        $member_to_pool{$dev} = $pool;
        $used_map{$dev} = 1;
        # Also add common variants
        $member_to_pool{"/dev/$dev"} = $pool;
        $member_to_pool{lc $dev} = $pool;
    }
    # If any partition is a member, mark its parent disk as used too (but don't add to member map)
    for my $dev_name (keys %devs) {
        for my $part (@{ $devs{$dev_name}{parts} }) {
            if ($member_to_pool{$part}) {
                $used_map{$dev_name} = 1;  # Mark parent as used, but DON'T add to member_to_pool
            }
        }
    }

    # Debug: optionally dump membership mapping when requested via URL param
    if ($in{'debug_map'}) {
        print "<div class='zfsguru-warn-block'>";
        print "<h4>Debug: ZFS member mapping</h4>";
        print "<pre>Member to pool mapping:\n";
        for my $k (sort keys %member_to_pool) { printf "%s => %s\n", $k, $member_to_pool{$k}; }
        print "\nUsed map keys:\n";
        for my $k (sort keys %used_map) { print "$k\n"; }
        print "</pre></div>";
    }

    # Helper to resolve pool name for a given id by trying multiple common variants
    sub _pool_for_id {
        my ($id, $member_ref, $glabel_ref) = @_;
        return '' unless defined $id && length $id;
        my %m = %{$member_ref};
        my %g = %{$glabel_ref};
        return $m{$id} if $m{$id};
        return $m{"/dev/$id"} if $m{"/dev/$id"};
        return $m{"gpt/$id"} if $m{"gpt/$id"};
        return $m{"/dev/gpt/$id"} if $m{"/dev/gpt/$id"};
        return $m{lc $id} if $m{lc $id};
        # Check glabel mapping
        if (exists $g{$id}) {
            my $t = $g{$id}; $t =~ s{^/dev/}{};
            return $m{$t} if $m{$t};
            return $m{"/dev/$t"} if $m{"/dev/$t"};
        }
        # Try fuzzy/ends-with matching against known member keys (covers variants like "/dev/gpt/TANK1" vs "da0p2")
        for my $k (keys %m) {
            next unless defined $k && length $k;
            if ($k eq $id or lc($k) eq lc($id)) { return $m{$k}; }
            if ($k =~ /\Q$id\E$/i) { return $m{$k}; }
            if ($id =~ /\Q$k\E$/i) { return $m{$k}; }
        }
        return '';
    }

    # Determine dynamic max parts count
    my $max_parts = 0;
    for my $d (keys %devs) {
        my $cnt = 0;
        if (ref $devs{$d}{parts} eq 'ARRAY') { $cnt = scalar @{ $devs{$d}{parts} }; }
        $max_parts = $cnt if $cnt > $max_parts;
    }
    $max_parts = 1 if $max_parts < 1;

    print "<table class='ui_table zfsguru-table-full'><tr><th>" . L("COL_DEVICE") . "</th>";
    for my $i (1..$max_parts) { print "<th>" . L("COL_PARTITION_SLICE") . "</th>"; }
    print "</tr>";

    foreach my $dev (sort keys %devs) {
        my $dinfo = $devs{$dev};
        my $dev_label = $dinfo->{scheme} ? "$dev ($dinfo->{scheme})" : $dev;
        # Check if parent disk is DIRECTLY a member (not through a partition)
        my $dev_pool = '';
        if ($member_to_pool{$dev} || $member_to_pool{"/dev/$dev"}) {
            $dev_pool = $member_to_pool{$dev} || $member_to_pool{"/dev/$dev"};
        }
        my $dev_display = $dev_label . ($dev_pool ? " [$dev_pool]" : '');
        my $has_partitions = (ref $dinfo->{parts} eq 'ARRAY' && @{$dinfo->{parts}});
        
        print "<tr><td>" . &html_escape($dev_display) . "</td>";

        my @parts = ref $dinfo->{parts} eq 'ARRAY' ? @{ $dinfo->{parts} } : ();
        for my $i (0..($max_parts-1)) {
            if (defined $parts[$i]) {
                my $p = $parts[$i];
                my $p_pool = _pool_for_id($p, \%member_to_pool, \%glabel_map) || '';
                my $p_is_boot = $boot_parts{$p};
                my $p_display = $p;
                $p_display .= ' [BOOT]' if $p_is_boot;
                $p_display .= " [$p_pool]" if $p_pool;
                if ($p_pool || $p_is_boot) {
                    print "<td><label class='zfsguru-muted'><input type='checkbox' name='disk_$p' value='1' disabled> " . &html_escape($p_display) . "</label></td>";
                } else {
                    print "<td><label><input type='checkbox' name='disk_$p' value='1'> " . &html_escape($p_display) . "</label></td>";
                }
            } else {
                print "<td></td>";
            }
        }
        print "</tr>";
    }
    print "</table>";
    print &ui_form_end([ [ "create_pool", L("BTN_CREATE_POOL") ] ]);
}

sub action_add_vdev {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);

    if ($in{'do_confirm_add_vdev'}) {
        my $vdev_type = $in{'vdev_type'} || 'stripe';
        my %valid_type = map { $_ => 1 } qw(stripe mirror raidz raidz2 raidz3);
        if (!$valid_type{$vdev_type}) {
            print &ui_print_error(L("ERR_INVALID_VDEV_TYPE"));
            return;
        }
        my @vdevs;
        for my $line (split /\n/, ($in{'vdev_list'} || '')) {
            $line =~ s/^\s+|\s+$//g;
            next unless length $line;
            my $n = zfsguru_lib::_normalize_dev_path($line);
            next unless $n;
            push @vdevs, $n;
        }
        my %seen;
        @vdevs = grep { !$seen{$_}++ } @vdevs;
        if (!@vdevs) {
            print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            return;
        }

        my $min = vdev_type_min_disks($vdev_type);
        if (@vdevs < $min) {
            print &ui_print_error(L("ERR_NOT_ENOUGH_DISKS_FOR_VDEV", $min, uc($vdev_type)));
            return;
        }

        if (!$in{'confirm_add_vdev'}) {
            print &ui_print_error(L("ERR_CONFIRM_ADD_VDEV_REQUIRED"));
            return;
        }
        my $force = $in{'add_vdev_force'} ? 1 : 0;
        if ($force && !$in{'confirm_add_vdev_force'}) {
            print &ui_print_error(L("ERR_CONFIRM_ADD_VDEV_FORCE_REQUIRED"));
            return;
        }

        my @cmd = ($zfsguru_lib::ZPOOL || '/sbin/zpool', 'add');
        push @cmd, '-f' if $force;
        push @cmd, $pool_name;
        push @cmd, $vdev_type if $vdev_type ne 'stripe';
        push @cmd, @vdevs;

        eval {
            must_run(@cmd);
            log_info("Added vdev(s) to pool $pool_name type=$vdev_type force=$force devices=" . join(',', @vdevs));
            print &ui_print_success(L("SUCCESS_DEVICES_ADDED", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_ADD_DEVICES_FAILED", $@));
        }
        return;
    }

    if ($in{'add_vdev'}) {
        my $vdev_type = $in{'vdev_type'} || 'stripe';
        my %valid_type = map { $_ => 1 } qw(stripe mirror raidz raidz2 raidz3);
        if (!$valid_type{$vdev_type}) {
            print &ui_print_error(L("ERR_INVALID_VDEV_TYPE"));
            return;
        }

        my @vdevs = selected_vdevs_from_form();
        if (!@vdevs) {
            print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            return;
        }
        my $min = vdev_type_min_disks($vdev_type);
        if (@vdevs < $min) {
            print &ui_print_error(L("ERR_NOT_ENOUGH_DISKS_FOR_VDEV", $min, uc($vdev_type)));
            return;
        }

        my @conflicts;
        for my $dev (@vdevs) {
            my $in_pool = device_in_zpool($dev);
            if ($in_pool) {
                push @conflicts, "$dev";
            }
        }
        if (@conflicts) {
            print &ui_print_error(L("ERR_VDEV_IN_POOL", join(', ', @conflicts)));
            return;
        }

        my @preview = ($zfsguru_lib::ZPOOL || '/sbin/zpool', 'add');
        my $force = $in{'add_vdev_force'} ? 1 : 0;
        push @preview, '-f' if $force;
        push @preview, $pool_name;
        push @preview, $vdev_type if $vdev_type ne 'stripe';
        push @preview, @vdevs;

        print &ui_subheading(L("SUB_CONFIRM_ADD_STORAGE", $pool_name));
        print "<div class='zfsguru-code-block'><b>" . L("LBL_COMMAND_TO_EXECUTE") . "</b><br>" .
              &html_escape(join(' ', @preview)) . "</div>";
        print &ui_alert(L("WARN_ADD_STORAGE_IMPACT"), 'warning');

        print &ui_form_start("advanced_pools.cgi", "post");
        print &ui_hidden("action", "add_vdev");
        print &ui_hidden("pool", $pool_name);
        print &ui_hidden("do_confirm_add_vdev", 1);
        print &ui_hidden("vdev_type", $vdev_type);
        print &ui_hidden("vdev_list", join("\n", @vdevs));
        print &ui_hidden("add_vdev_force", $force ? 1 : 0);
        print &ui_table_start(L("TABLE_ADD_VDEV_CONFIRM"), "width=100%", 2);
        print &ui_table_row(L("ROW_VDEV_TYPE"), &html_escape(uc($vdev_type)));
        print &ui_table_row(L("ROW_DISKS"), &html_escape(join(', ', @vdevs)));
        print &ui_table_row(L("ROW_FORCE"), $force ? L("VALUE_YES") : L("VALUE_NO"));
        print &ui_table_row(L("ROW_CONFIRM"),
            &ui_checkbox("confirm_add_vdev", 1, L("LBL_CONFIRM_ADD_VDEV"), 0));
        print &ui_table_row(L("ROW_CONFIRM_FORCE"),
            &ui_checkbox("confirm_add_vdev_force", 1, L("LBL_CONFIRM_ADD_VDEV_FORCE"), 0));
        print &ui_table_end();
        print &ui_form_end([ [ "do_confirm_add_vdev", L("BTN_PROCEED") ] ]);
        return;
    }

    print &ui_subheading(L("SUB_ADD_STORAGE", $pool_name));
    print_pool_action_help(
        what    => "Adds new vdev(s) to an existing pool.",
        benefit => "Expands capacity or adds redundancy/performance tiers.",
        risk    => "Topology is mostly permanent; bad layout can hurt resilience."
    );
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "add_vdev");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("add_vdev", 1);

    print &ui_table_start(L("TABLE_ADD_VDEV_CONFIG"), "width=100%", 2);
    print &ui_table_row(L("ROW_VDEV_TYPE"), &ui_select("vdev_type", "stripe", [
        [ "stripe", L("OPT_RAID0_STRIPE") ],
        [ "mirror", L("OPT_RAID1_MIRROR") ],
        [ "raidz", L("OPT_RAIDZ") ],
        [ "raidz2", L("OPT_RAIDZ2") ],
        [ "raidz3", L("OPT_RAIDZ3") ],
    ]));
    print &ui_table_row(L("ROW_FORCE"),
        &ui_checkbox("add_vdev_force", 1, L("LBL_ADD_VDEV_FORCE"), 0) .
        "<br><small>" . L("HINT_ADD_VDEV_FORCE") . "</small>");
    print &ui_table_end();

    my %seen_target;
    my @targets;
    my $disks = disk_list();
    for my $disk (@$disks) {
        next unless is_disk_name($disk);
        push @targets, "/dev/$disk";
        push @targets, glob("/dev/${disk}p*");
        push @targets, glob("/dev/${disk}s*");
    }
    @targets = grep { defined $_ && $_ =~ m{^/dev/} && !$seen_target{$_}++ } @targets;

    my @heads = (L("COL_DEVICE"), L("COL_STATUS"), L("COL_OPTIONS"), L("COL_ACTION"));
    my @data;
    for my $dev (@targets) {
        my $name = $dev; $name =~ s{^/dev/}{};
        my $state = L("VALUE_AVAILABLE");
        my @notes;
        my $disabled = 0;

        my $in_pool = device_in_zpool($dev);
        if ($in_pool) {
            $state = L("VALUE_IN_USE");
            push @notes, "Already member of an existing pool";
            $disabled = 1;
        }
        my $mnt = device_mountpoints($dev);
        if ($mnt && @$mnt) {
            push @notes, L("MSG_DEVICE_MOUNTED", join(', ', @$mnt));
        }
        if ($name =~ /^([A-Za-z0-9:_\-\.]+)p(\d+)$/) {
            my ($d, $idx) = ($1, $2);
            my $plist = gpart_list_partitions_info($d);
            my $ptype = '';
            if (ref($plist) eq 'ARRAY') {
                for my $pi (@$plist) {
                    next unless ref($pi) eq 'HASH';
                    if (defined $pi->{index} && $pi->{index} eq $idx) {
                        $ptype = $pi->{type} || '';
                        last;
                    }
                }
            }
            if ($ptype =~ /^(?:freebsd-boot|efi|bios-boot)$/i) {
                $state = L("VALUE_RESERVED");
                push @notes, L("MSG_ADD_VDEV_BOOT_PARTITION", $ptype);
                $disabled = 1;
            }
        }

        my $cb = $disabled
            ? "<label class='zfsguru-muted'><input type='checkbox' disabled> " . &html_escape($name) . "</label>"
            : &ui_checkbox("disk_$name", 1, $name, 0);

        push @data, [
            &html_escape($dev),
            &html_escape($state),
            &html_escape(@notes ? join('; ', @notes) : '-'),
            $cb,
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_SELECT_DISKS_TO_ADD"), L("VALUE_NONE"));
    print &ui_form_end([ [ "add_vdev", L("BTN_ADD_DISKS") ] ]);
}

sub pool_needs_attention {
    my ($pool_name, $health) = @_;
    return (0, '') unless defined $pool_name && is_pool_name($pool_name);
    return (1, 'Pool health is not ONLINE') if defined($health) && $health ne '' && $health ne 'ONLINE';

    my ($rc, $out, $err) = run_cmd(($zfsguru_lib::ZPOOL || '/sbin/zpool'), 'status', $pool_name);
    return (0, '') if $rc != 0 || !$out;

    my $state = '';
    my $status = '';
    my $in_status = 0;
    for my $line (split /\n/, $out) {
        if ($line =~ /^\s*state:\s*(.+?)\s*$/i) {
            $state = $1;
            next;
        }
        if ($line =~ /^\s*status:\s*(.*?)\s*$/i) {
            $status = $1;
            $in_status = 1;
            next;
        }
        if ($in_status) {
            last if $line =~ /^\s*(?:action|scan|config|errors|see):/i;
            last if $line =~ /^\S/;
            $line =~ s/^\s+//;
            $status .= " $line" if length $line;
        }
    }
    $status =~ s/\s+/ /g;
    $status =~ s/^\s+|\s+$//g;

    if ($state ne '' && uc($state) ne 'ONLINE') {
        return (1, $status || "state: $state");
    }
    if ($status =~ /\b(?:degraded|fault|error|offline|unavail|removed|corrupt|suspended|insufficient)\b/i) {
        return (1, $status);
    }
    return (0, $status);
}

sub action_replace {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);
    
    if ($in{'do_replace'}) {
        my $old_dev = $in{'old_device'};
        my $new_dev = $in{'new_device'};
        
        eval {
            zpool_replace($pool_name, $old_dev, $new_dev);
            log_info("Replaced device in pool $pool_name: $old_dev -> $new_dev");
            print &ui_print_success(L("SUCCESS_DEVICE_REPLACE_STARTED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DEVICE_REPLACE_FAILED", $@));
        }
        return;
    }
    
    my $status_text = zpool_status($pool_name);
    print &ui_subheading(L("SUB_REPLACE_DEVICE", $pool_name));
    print_pool_action_help(
        what    => "Replaces a selected pool device with another one.",
        benefit => "Used for failed disk swap or proactive migration.",
        risk    => "Wrong source/target choice can start risky resilver operations."
    );
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "replace");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("do_replace", 1);
    
    print &ui_table_start(L("TABLE_REPLACE_DEVICE"), "width=100%", 2);
    
    my %seen;
    my @old_devices;
    if (defined $status_text && length $status_text) {
        for my $line (split /\n/, $status_text) {
            next unless $line =~ /^\s+(\S+)\s+(ONLINE|OFFLINE|DEGRADED|FAULTED|REMOVED|UNAVAIL)\b/;
            my $dev = $1;
            next if $dev eq $pool_name;
            next if $dev =~ /^(mirror|raidz\d*|spares|logs|cache|special|dedup|replacing)/;
            next if $seen{$dev}++;
            push @old_devices, [ $dev, $dev ];
        }
    }

    if (!@old_devices) {
        print &ui_print_error(L("ERR_NO_REPLACEABLE_DEVICES"));
    }
    
    print &ui_table_row(L("ROW_DEVICE_TO_REPLACE"), &ui_select("old_device", "", \@old_devices));

    my @new_candidates;
    my $dl = disk_list() || [];
    for my $disk (@$dl) {
        next unless is_disk_name($disk);
        push @new_candidates, $disk;
        push @new_candidates, map { s{^/dev/}{}r } glob("/dev/${disk}p*");
        push @new_candidates, map { s{^/dev/}{}r } glob("/dev/${disk}s*");
    }
    my %new_seen;
    my @new_devices;
    for my $cand (@new_candidates) {
        next unless defined $cand && $cand ne '';
        next if $new_seen{$cand}++;
        my $dev_path = "/dev/$cand";

        # Replacement target must not be already used by any pool.
        my $in_pool = device_in_zpool($dev_path);
        next if $in_pool && @$in_pool;

        # Skip boot/system helper partitions.
        if ($cand =~ /^([A-Za-z0-9:_\-\.]+)p(\d+)$/) {
            my ($d, $idx) = ($1, $2);
            my $plist = gpart_list_partitions_info($d);
            if (ref($plist) eq 'ARRAY') {
                my $ptype = '';
                for my $pi (@$plist) {
                    next unless ref($pi) eq 'HASH';
                    next unless defined $pi->{index} && $pi->{index} eq $idx;
                    $ptype = $pi->{type} || '';
                    last;
                }
                next if $ptype =~ /^(?:freebsd-boot|efi|bios-boot)$/i;
            }
        }
        push @new_devices, [ $cand, $cand ];
    }
    @new_devices = [ [ '', '-' ] ] unless @new_devices;
    print &ui_table_row(L("ROW_NEW_DEVICE"), &ui_select("new_device", ($in{'new_device'} || ''), \@new_devices));
    
    print &ui_table_end();
    print &ui_form_end([ [ "do_replace", L("BTN_REPLACE") ] ]);
}

sub action_scrub {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);
    
    my $do_start = $in{'start_scrub'} ? 1 : 0;
    my $do_stop  = $in{'stop_scrub'}  ? 1 : 0;

    if ($do_start || $do_stop) {
        my $stop = $do_stop ? 1 : 0;
        eval {
            zpool_scrub($pool_name, $stop);
            log_info("Scrub " . ($stop ? "stopped" : "started") . " on pool $pool_name");
            print &ui_print_success($stop ? L("SUCCESS_SCRUB_STOPPED") : L("SUCCESS_SCRUB_STARTED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SCRUB_FAILED", $@));
        }
        return;
    }
    
    my $status_text = zpool_status($pool_name);
    my $scan_status = L("STATUS_NO_SCRUB");
    if (defined $status_text && $status_text =~ /^\s*scan:\s+(.+)$/m) {
        $scan_status = $1;
    }
    print &ui_subheading(L("SUB_SCRUB_MANAGEMENT", $pool_name));
    print_pool_action_help(
        what    => "Starts or stops data scrub on the pool.",
        benefit => "Detects/corrects latent checksum errors early.",
        risk    => "Can increase disk load and impact performance during scrub."
    );
    print L("LBL_CURRENT_STATUS") . ": " . &html_escape($scan_status) . "<br><br>";
    
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "scrub");
    print &ui_hidden("pool", $pool_name);
    print &ui_submit(L("BTN_START_SCRUB"), "start_scrub") . " ";
    print &ui_submit(L("BTN_STOP_SCRUB"), "stop_scrub");
    print &ui_form_end();
}

sub action_import {
    my $pool_id = $in{'pool_id'} // '';
    my $force_import = $in{'force_import'} ? 1 : 0;
    my $import_destroyed = $in{'import_destroyed'} ? 1 : 0;
    my $search_path = defined($in{'search_path'}) ? $in{'search_path'} : '';
    $search_path =~ s/^\s+|\s+$//g if defined $search_path;

    my $list = sub {
        my %opt;
        $opt{import_destroyed} = 1 if $import_destroyed;
        if (defined $search_path && length $search_path) {
            if (!is_mountpoint($search_path)) {
                print &ui_print_error(L("ERR_IMPORT_SEARCH_PATH", $search_path));
                return undef;
            }
            $opt{search_path} = $search_path;
        }
        return zpool_import_list(%opt);
    };

    my $find_entry_by_id = sub {
        my ($pools, $id) = @_;
        return undef unless $pools && ref($pools) eq 'ARRAY';
        return undef unless defined $id && length $id;
        for my $p (@$pools) {
            next unless defined $p->{id};
            return $p if lc($p->{id}) eq lc($id);
        }
        return undef;
    };

    if ($in{'do_import'}) {
        if (!$in{'confirm_understand_import'}) {
            print &ui_print_error(L("ERR_CONFIRM_IMPORT_REQUIRED"));
            return;
        }
        if (!$pool_id || $pool_id !~ /^[0-9a-f]+$/i) {
            print &ui_print_error(L("ERR_INVALID_POOL_ID", $pool_id));
            return;
        }

        my $importables = $list->();
        return unless $importables;

        my $entry = $find_entry_by_id->($importables, $pool_id);
        if (!$entry) {
            print &ui_print_error(L("ERR_IMPORT_POOL_NOT_FOUND", $pool_id));
            return;
        }

        eval {
            zpool_import(
                pool             => $pool_id,
                force            => $force_import,
                import_destroyed => $import_destroyed,
                devdir           => (defined $search_path && length $search_path) ? $search_path : undef,
            );
            log_info("Imported pool: id=$pool_id force=$force_import destroyed=$import_destroyed path=" . ($search_path || '-'));
            print &ui_print_success(L('IMPORT_SUCCESS'));
        };
        if ($@) {
            print &ui_print_error(L('IMPORT_FAILED', $@));
        }
        return;
    }

    if ($in{'confirm_import'}) {
        if (!$pool_id || $pool_id !~ /^[0-9a-f]+$/i) {
            print &ui_print_error(L("ERR_INVALID_POOL_ID", $pool_id));
            return;
        }

        my $importables = $list->();
        return unless $importables;

        my $entry = $find_entry_by_id->($importables, $pool_id);
        if (!$entry) {
            print &ui_print_error(L("ERR_IMPORT_POOL_NOT_FOUND", $pool_id));
            return;
        }

        print &ui_print_error_header(L("HDR_IMPORT_POOL"));
        print "<p>" . L("CONFIRM_IMPORT_POOL", &html_escape($entry->{name} || ''), &html_escape($pool_id)) . "</p>";

        print "<div class='zfsguru-danger-block'>";
        my @cmd_preview = ('zpool', 'import');
        push @cmd_preview, '-d', $search_path if defined $search_path && length $search_path;
        push @cmd_preview, '-D' if $import_destroyed;
        push @cmd_preview, '-f' if $force_import;
        push @cmd_preview, $pool_id;
        print &html_escape(join(' ', @cmd_preview));
        print "</div>";

        print &ui_form_start("advanced_pools.cgi", "post");
        print &ui_hidden("action", "import");
        print &ui_hidden("pool_id", $pool_id);
        print &ui_hidden("confirm_import", 1);
        print &ui_hidden("import_destroyed", 1) if $import_destroyed;
        print &ui_hidden("search_path", $search_path) if defined $search_path && length $search_path;

        print &ui_table_start(L("TABLE_IMPORT_OPTIONS"), "width=100%", 2);
        print &ui_table_row(L("ROW_IMPORT_FORCE"), &ui_checkbox("force_import", 1, L("LBL_IMPORT_FORCE"), $force_import));
        print &ui_table_row(L("ROW_IMPORT_CONFIRM"), &ui_checkbox("confirm_understand_import", 1, L("LBL_CONFIRM_UNDERSTAND_IMPORT"), 0));
        print &ui_table_end();

        print &ui_submit(L("BTN_IMPORT"), "do_import") . " ";
        print &ui_link("advanced_pools.cgi?action=import", L("BTN_CANCEL"));
        print &ui_form_end();
        return;
    }

    print &ui_subheading(L("SUB_IMPORT_POOLS"));
    print_pool_action_help(
        what    => "Imports pools discovered on connected devices.",
        benefit => "Re-attaches exported or moved pools quickly.",
        risk    => "Importing wrong/foreign metadata can conflict with existing setup."
    );

    print &ui_form_start("advanced_pools.cgi", "get");
    print &ui_hidden("action", "import");
    print &ui_table_start(L("TABLE_IMPORT_OPTIONS"), "width=100%", 2);
    print &ui_table_row(L("ROW_IMPORT_SEARCH_PATH"), &ui_textbox("search_path", $search_path, 30) .
        "<br><small>" . L("HINT_IMPORT_SEARCH_PATH") . "</small>");
    print &ui_table_row(L("ROW_IMPORT_INCLUDE_DESTROYED"), &ui_checkbox("import_destroyed", 1, L("LBL_IMPORT_INCLUDE_DESTROYED"), $import_destroyed));
    print &ui_table_end();
    print &ui_form_end([ [ "refresh", L("BTN_REFRESH") ] ]);

    my $importables = $list->();
    return unless $importables;

    if (!@$importables) {
        print &ui_print_error(L('IMPORT_NOPOOLS'));
        return;
    }

    my @heads = (L("COL_POOL"), L("COL_ID"), L("COL_STATUS"), "Status Detail", L("COL_ACTION"));
    my @data;
    for my $p (@$importables) {
        my $id = $p->{id} // '';
        my $act_url = "advanced_pools.cgi?action=import&confirm_import=1&pool_id=" . &url_encode($id);
        $act_url .= "&import_destroyed=1" if $import_destroyed;
        $act_url .= "&search_path=" . &url_encode($search_path) if defined $search_path && length $search_path;

        push @data, [
            &html_escape($p->{name} // ''),
            &html_escape($id),
            &html_escape($p->{state} // ''),
            &html_escape($p->{status} // ''),
            &ui_link_icon($act_url, L("BTN_IMPORT"), undef, { class => 'primary' }),
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_AVAILABLE_POOLS"), L("IMPORT_NOPOOLS"));
}

sub action_export {
    my $pool_name = $in{'pool'} // '';
    die "Invalid pool name" unless is_pool_name($pool_name);

    if ($in{'do_export'}) {
        if (!$in{'confirm_understand_export'}) {
            print &ui_print_error(L("ERR_CONFIRM_EXPORT_REQUIRED"));
            return;
        }

        eval {
            zpool_export($pool_name);
            log_info("Exported pool: $pool_name");
            print &ui_print_success(L("SUCCESS_POOL_EXPORTED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_POOL_EXPORT_FAILED", $@));
        }
        return;
    }

    my $datasets = zfs_list([qw(name mountpoint)], '-r', $pool_name);
    my @mounts = ();
    if ($datasets && ref($datasets) eq 'ARRAY') {
        for my $ds (@$datasets) {
            my $mp = $ds->{mountpoint} // '';
            next if $mp eq '' || $mp eq '-' || $mp eq 'none';
            push @mounts, "$ds->{name} -> $mp";
        }
    }

    print &ui_print_error_header(L("HDR_EXPORT_POOL"));
    print_pool_action_help(
        what    => "Exports the pool and detaches it from the host.",
        benefit => "Safe handoff before moving disks/system migration.",
        risk    => "Services using this pool will lose access until re-import."
    );
    print "<p>" . L("CONFIRM_EXPORT_POOL", &html_escape($pool_name)) . "</p>";

    print "<div class='zfsguru-danger-block'>";
    print &html_escape("zpool export $pool_name");
    print "</div>";

    if (@mounts) {
        print &ui_subheading(L("SUB_EXPORT_IMPACT"));
        print "<pre class='zfsguru-code-block'>" . &html_escape(join("\n", @mounts)) . "</pre>";
    }

    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "export");
    print &ui_hidden("pool", $pool_name);
    print &ui_checkbox("confirm_understand_export", 1, L("LBL_CONFIRM_UNDERSTAND_EXPORT"), 0);
    print "<br><br>";
    print &ui_submit(L("BTN_EXPORT_POOL"), "do_export") . " ";
    print &ui_link("advanced_pools.cgi?action=view&pool=" . &url_encode($pool_name), L("BTN_CANCEL"));
    print &ui_form_end();
}

sub action_destroy {
    my $pool_name = $in{'pool'} // '';

    if ($in{'do_destroy'}) {
        die "Invalid pool name" unless is_pool_name($pool_name);

        unless ($in{'confirm_understand'}) {
            print &ui_print_error(L("ERR_CONFIRM_DESTROY_REQUIRED"));
            return;
        }

        # Force destroy requires an extra explicit confirmation.
        if ($in{'force_destroy'} && !$in{'confirm_force'}) {
            print &ui_print_error_header(L('HDR_FORCE_DESTROY_CONFIRM'));
            print "<p class='zfsguru-text-bad'>" . L("MSG_FORCE_DESTROY_WARNING") . "</p>";
            print "<div class='zfsguru-danger-block'>" . &html_escape("zpool destroy -f $pool_name") . "</div>";

            print &ui_form_start('advanced_pools.cgi', 'post');
            print &ui_hidden('action', 'destroy');
            print &ui_hidden('pool', $pool_name);
            print &ui_hidden('force_destroy', 1);
            print &ui_hidden('confirm_understand', 1);
            print &ui_table_start(L("TABLE_FORCE_DESTROY_CONFIRM"), "width=100%", 2);
            print &ui_table_row(L("ROW_FORCE_CONFIRM"), &ui_checkbox('confirm_force', 1, L("LBL_CONFIRM_FORCE_DESTROY"), 0));
            print &ui_table_end();
            print &ui_submit(L('BTN_CONFIRM_FORCE_DESTROY'), 'do_destroy') . " ";
            print &ui_link("advanced_pools.cgi?action=destroy", L("BTN_CANCEL"));
            print &ui_form_end();
            return;
        }

        eval {
            require_root();
            my @cmd = ($zfsguru_lib::ZPOOL || '/sbin/zpool', 'destroy');
            push @cmd, '-f' if $in{'force_destroy'};
            push @cmd, $pool_name;
            log_info("Destroying pool: $pool_name (force=" . ($in{'force_destroy'} ? '1' : '0') . ")");
            must_run(@cmd);
            log_info("Destroyed pool: $pool_name");
            print &ui_print_success(L("DESTROY_SUCCESS", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("DESTROY_FAILED", $@));
        }
    }

    print &ui_subheading(L('SUB_DESTROY_POOL'));
    print_pool_action_help(
        what    => "Destroys selected pool metadata and all data references.",
        benefit => "Clean teardown of obsolete pools.",
        risk    => "Irreversible data loss."
    );
    my $pools = zpool_list();
    if (!@$pools) {
        print &ui_print_error(L('NO_POOLS'));
        return;
    }

    print "<p class='zfsguru-text-bad'>" . L("MSG_REVIEW_COMMAND") . " " .
          "Check " . L("ROW_CONFIRM") . " before destroying a pool." . "</p>";

    my @heads = (L("COL_POOL"), L("COL_STATUS"), L("COL_ACTIONS"));
    my @data;
    for my $p (@$pools) {
        my $name = $p->{name} // '';
        next unless $name ne '';

        my $confirm_html = &ui_checkbox("confirm_understand", 1, L("ROW_CONFIRM"), 0);
        my $force_html   = &ui_checkbox("force_destroy", 1, L("ROW_FORCE_DESTROY"), 0);

        my $actions_html = &ui_form_start('advanced_pools.cgi', 'post');
        $actions_html .= &ui_hidden('action', 'destroy');
        $actions_html .= &ui_hidden('pool', $name);
        $actions_html .= "$confirm_html<br>$force_html<br>";
        $actions_html .= "<input type='submit' name='do_destroy' value='" . &html_escape(L('BTN_DESTROY_POOL')) .
                         "' style='background:#d93025;color:#fff;border:1px solid #b3261e;padding:4px 10px;border-radius:3px;cursor:pointer;'>";
        $actions_html .= &ui_form_end();

        push @data, [
            &html_escape($name),
            &html_escape($p->{health} // $p->{status} // ''),
            $actions_html,
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_POOLS"), L("NO_POOLS"));
}

sub action_rename {
    my $pool_name = $in{'pool'} || '';
    die "Invalid pool name" unless is_pool_name($pool_name);

    if ($in{'do_rename'}) {
        my $new_name = $in{'new_pool_name'} || '';
        if (!is_pool_name($new_name)) {
            print &ui_print_error(L("ERR_INVALID_POOL_NAME", $new_name));
            return;
        }
        eval {
            zpool_rename($pool_name, $new_name);
            log_info("Renamed pool: $pool_name -> $new_name");
            print &ui_print_success(L("SUCCESS_POOL_RENAMED", $pool_name, $new_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_POOL_RENAME_FAILED", $@));
        }
        return;
    }

    print &ui_subheading(L("SUB_POOL_RENAME", $pool_name));
    print_pool_action_help(
        what    => "Renames the pool identifier.",
        benefit => "Cleaner naming and easier operational clarity.",
        risk    => "Scripts/configs referencing old name must be updated."
    );
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "rename");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("do_rename", 1);
    my $rename_default = exists $in{'new_pool_name'} ? ($in{'new_pool_name'} // '') : $pool_name;
    print &ui_table_start(L("TABLE_RENAME_CONFIG"), "width=100%", 2);
    print &ui_table_row(L("ROW_CURRENT_POOL"), &html_escape($pool_name));
    print &ui_table_row(L("ROW_NEW_POOL_NAME"), &ui_textbox("new_pool_name", $rename_default, 30));
    print &ui_table_end();
    print &ui_form_end([ [ "do_rename", L("BTN_RENAME_POOL") ] ]);
}

sub action_upgrade {
    my $pool_name = $in{'pool'} || '';
    die "Invalid pool name" unless is_pool_name($pool_name);

    my $all_props = zpool_properties($pool_name);
    my $prop_value = sub {
        my ($props_ref, $key) = @_;
        return '' unless ref($props_ref) eq 'HASH' && defined $key;
        my $raw = $props_ref->{$key};
        return ref($raw) eq 'HASH' ? ($raw->{value} // '') : (defined($raw) ? $raw : '');
    };
    my $version = $prop_value->($all_props, 'version');
    $version = L("VALUE_UNKNOWN") if !defined($version) || $version eq '';
    my ($enabled, $active, $disabled) = (0, 0, 0);
    if (ref($all_props) eq 'HASH') {
        for my $k (keys %{$all_props}) {
            next unless $k =~ /^feature\@/;
            my $v = lc($prop_value->($all_props, $k) // '');
            $enabled++  if $v eq 'enabled' || $v eq 'active';
            $active++   if $v eq 'active';
            $disabled++ if $v eq 'disabled';
        }
    }
    my $needs_upgrade = 1;
    if ($version eq '-') {
        $needs_upgrade = $disabled > 0 ? 1 : 0;
    }
    elsif ($version =~ /^\d+$/) {
        $needs_upgrade = ($version + 0) < 5000 ? 1 : 0;
    }

    if ($in{'do_upgrade'}) {
        if (!$needs_upgrade) {
            print &ui_alert(L("WARN_POOL_UPGRADE_NOT_NEEDED"), 'warning');
            return;
        }
        if (!$in{'confirm_upgrade'}) {
            print &ui_print_error(L("ERR_CONFIRM_UPGRADE_REQUIRED"));
            return;
        }
        eval {
            zpool_upgrade($pool_name);
            log_info("Upgraded pool: $pool_name");
            print &ui_print_success(L("SUCCESS_POOL_UPGRADED", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_POOL_UPGRADE_FAILED", $@));
        }
        return;
    }

    if ($version eq '-') {
        $version = ($enabled > 0)
            ? L("VALUE_POOL_FEATURE_FLAGS_COUNT", $enabled, $active)
            : L("VALUE_POOL_FEATURE_FLAGS");
    }

    print &ui_subheading(L("SUB_POOL_UPGRADE", $pool_name));
    print_pool_action_help(
        what    => "Upgrades on-disk pool feature flags/version.",
        benefit => "Enables newer ZFS features and fixes.",
        risk    => "May reduce backward compatibility with older systems."
    );
    print &ui_table_start(L("TABLE_POOL_UPGRADE"), "width=100%", 2);
    print &ui_table_row(L("ROW_CURRENT_VERSION"), &html_escape($version));
    print &ui_table_end();
    if (!$needs_upgrade) {
        print &ui_alert(L("WARN_POOL_UPGRADE_NOT_NEEDED"), 'warning');
    }
    else {
        print "<p>" . L("MSG_POOL_UPGRADE_WARNING") . "</p>";
        print &ui_form_start("advanced_pools.cgi", "post");
        print &ui_hidden("action", "upgrade");
        print &ui_hidden("pool", $pool_name);
        print &ui_hidden("do_upgrade", 1);
        print &ui_checkbox("confirm_upgrade", 1, L("LBL_CONFIRM_UPGRADE"), 0);
        print "<br><br>";
        print &ui_submit(L("BTN_UPGRADE_POOL"), "do_upgrade");
        print &ui_form_end();
    }
}

sub action_bootfs {
    my $pool_name = $in{'pool'} || '';
    die "Invalid pool name" unless is_pool_name($pool_name);

    if ($in{'set_bootfs'}) {
        my $ds = $in{'bootfs_ds'};
        $ds = '' if !defined $ds || $ds eq '-';
        if (length $ds && !is_dataset_name($ds)) {
            print &ui_print_error(L("ERR_INVALID_DATASET", $ds));
            return;
        }
        eval {
            zpool_set_bootfs($pool_name, $ds);
            log_info("Set bootfs for $pool_name to " . ($ds || '-'));
            print &ui_print_success(L("SUCCESS_BOOTFS_SET", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_BOOTFS_SET_FAILED", $@));
        }
    }

    my $props = zpool_properties($pool_name, 'bootfs');
    my $bootfs_raw = $props->{bootfs};
    my $cur = (ref($bootfs_raw) eq 'HASH' ? ($bootfs_raw->{value} // '') : (defined($bootfs_raw) ? $bootfs_raw : ''));
    $cur = '-' if !defined($cur) || $cur eq '' || $cur eq '-';
    my $datasets = zfs_list([qw(name)], '-r', $pool_name);
    my @opts = ( [ '-', '-' ] );
    for my $ds (@$datasets) {
        push @opts, [ $ds->{name}, $ds->{name} ];
    }

    print &ui_subheading(L("SUB_POOL_BOOTFS", $pool_name));
    print_pool_action_help(
        what    => "Sets default boot dataset for this pool.",
        benefit => "Controls which dataset bootloaders should start from.",
        risk    => "Wrong bootfs can cause boot failure or wrong environment."
    );
    print &ui_table_start(L("TABLE_BOOTFS"), "width=100%", 2);
    print &ui_table_row(L("ROW_BOOTFS_CURRENT"), &html_escape($cur));
    print &ui_table_end();

    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "bootfs");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("set_bootfs", 1);
    print &ui_table_start(L("TABLE_BOOTFS_SET"), "width=100%", 2);
    print &ui_table_row(L("ROW_BOOTFS_DATASET"), &ui_select("bootfs_ds", ($cur ne '-' ? $cur : '-'), \@opts));
    print &ui_table_end();
    print &ui_form_end([ [ "set_bootfs", L("BTN_SET_BOOTFS") ] ]);
}

sub action_cache {
    my $pool_name = $in{'pool'} || '';
    die "Invalid pool name" unless is_pool_name($pool_name);
    my $xnav_h = '';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $xnav_h = &ui_hidden("xnavigation", $in{'xnavigation'});
    }

    my $status_text = zpool_status($pool_name) || '';
    my ($groups, $used) = pool_special_devices($status_text, $pool_name);
    my @cache = @{ $groups->{cache} || [] };

    if ($in{'add_cache'}) {
        my @vdevs = selected_disks_from_form();
        if (!@vdevs) {
            print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            return;
        }
        eval {
            zpool_add_cache($pool_name, @vdevs);
            log_info("Added cache devices to $pool_name: " . join(',', @vdevs));
            print &ui_print_success(L("SUCCESS_CACHE_ADDED", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_CACHE_ADD_FAILED", $@));
        }
    }

    if ($in{'remove_cache'}) {
        my $dev = $in{'cache_device'} || '';
        if ($dev) {
            eval {
                zpool_remove($pool_name, $dev);
                log_info("Removed cache device from $pool_name: $dev");
                print &ui_print_success(L("SUCCESS_CACHE_REMOVED", $pool_name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_CACHE_REMOVE_FAILED", $@));
            }
        }
    }

    # Re-read status after add/remove so current/available device sections stay in sync.
    $status_text = zpool_status($pool_name) || '';
    ($groups, $used) = pool_special_devices($status_text, $pool_name);
    @cache = @{ $groups->{cache} || [] };

    print &ui_subheading(L("SUB_POOL_CACHE", $pool_name));
    print_pool_action_help(
        what    => "Manages L2ARC cache devices for the pool.",
        benefit => "Can improve read latency for repeated data.",
        risk    => "Extra complexity; limited benefit on some workloads."
    );
    my @cache_heads = (L("COL_DEVICE"), L("COL_ACTIONS"));
    my @cache_data;
    for my $dev (@cache) {
        my $remove_btn = "<form method='post' action='advanced_pools.cgi' style='display:inline'>"
                       . &ui_hidden("action", "cache")
                       . &ui_hidden("pool", $pool_name)
                       . $xnav_h
                       . &ui_hidden("remove_cache", 1)
                       . &ui_hidden("cache_device", $dev)
                       . "<input type='submit' class='ui_submit' value='" . &html_escape(L("BTN_REMOVE_CACHE"))
                       . "' style='background:#d9534f;color:#fff;border-color:#d9534f'>"
                       . "</form>";
        push @cache_data, [ &html_escape($dev), $remove_btn ];
    }
    print &ui_columns_table(\@cache_heads, 100, \@cache_data, undef, 1, L("TABLE_CACHE_DEVICES"), L("VALUE_NONE"));

    print &ui_hr();
    print &ui_subheading(L("SUB_ADD_CACHE"));
    print "<p><small>Cache devices can be full disks or partition/slice entries.</small></p>";
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "cache");
    print &ui_hidden("pool", $pool_name);
    print $xnav_h if $xnav_h;
    print &ui_hidden("add_cache", 1);
    print &ui_table_start(L("TABLE_SELECT_CACHE"), "width=100%", 2);
    render_device_selector_rows(used => $used, name_prefix => 'disk_');
    print &ui_table_end();
    print &ui_form_end([ [ "add_cache", L("BTN_ADD_CACHE") ] ]);
}

sub action_slog {
    my $pool_name = $in{'pool'} || '';
    die "Invalid pool name" unless is_pool_name($pool_name);
    my $xnav_h = '';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $xnav_h = &ui_hidden("xnavigation", $in{'xnavigation'});
    }

    my $status_text = zpool_status($pool_name) || '';
    my ($groups, $used) = pool_special_devices($status_text, $pool_name);
    my @logs = @{ $groups->{slog} || [] };

    if ($in{'add_slog'}) {
        my @vdevs = selected_disks_from_form();
        if (!@vdevs) {
            print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            return;
        }
        eval {
            zpool_add_log($pool_name, @vdevs);
            log_info("Added slog devices to $pool_name: " . join(',', @vdevs));
            print &ui_print_success(L("SUCCESS_SLOG_ADDED", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SLOG_ADD_FAILED", $@));
        }
    }

    if ($in{'remove_slog'}) {
        my $dev = $in{'slog_device'} || '';
        if ($dev) {
            eval {
                zpool_remove($pool_name, $dev);
                log_info("Removed slog device from $pool_name: $dev");
                print &ui_print_success(L("SUCCESS_SLOG_REMOVED", $pool_name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SLOG_REMOVE_FAILED", $@));
            }
        }
    }

    # Re-read status after add/remove so current/available device sections stay in sync.
    $status_text = zpool_status($pool_name) || '';
    ($groups, $used) = pool_special_devices($status_text, $pool_name);
    @logs = @{ $groups->{slog} || [] };

    print &ui_subheading(L("SUB_POOL_SLOG", $pool_name));
    print_pool_action_help(
        what    => "Manages dedicated ZIL/SLOG log devices.",
        benefit => "Improves sync write latency for sync-heavy workloads.",
        risk    => "Failed/slow SLOG can reduce performance or resilience."
    );
    my @slog_heads = (L("COL_DEVICE"), L("COL_ACTIONS"));
    my @slog_data;
    for my $dev (@logs) {
        my $remove_btn = "<form method='post' action='advanced_pools.cgi' style='display:inline'>"
                       . &ui_hidden("action", "slog")
                       . &ui_hidden("pool", $pool_name)
                       . $xnav_h
                       . &ui_hidden("remove_slog", 1)
                       . &ui_hidden("slog_device", $dev)
                       . "<input type='submit' class='ui_submit' value='" . &html_escape(L("BTN_REMOVE_SLOG"))
                       . "' style='background:#d9534f;color:#fff;border-color:#d9534f'>"
                       . "</form>";
        push @slog_data, [ &html_escape($dev), $remove_btn ];
    }
    print &ui_columns_table(\@slog_heads, 100, \@slog_data, undef, 1, L("TABLE_SLOG_DEVICES"), L("VALUE_NONE"));

    print &ui_hr();
    print &ui_subheading(L("SUB_ADD_SLOG"));
    print "<p><small>SLOG devices can be full disks or partition/slice entries.</small></p>";
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "slog");
    print &ui_hidden("pool", $pool_name);
    print $xnav_h if $xnav_h;
    print &ui_hidden("add_slog", 1);
    print &ui_table_start(L("TABLE_SELECT_SLOG"), "width=100%", 2);
    render_device_selector_rows(used => $used, name_prefix => 'disk_');
    print &ui_table_end();
    print &ui_form_end([ [ "add_slog", L("BTN_ADD_SLOG") ] ]);
}

sub action_spare {
    my $pool_name = $in{'pool'} || '';
    die "Invalid pool name" unless is_pool_name($pool_name);

    my $status_text = zpool_status($pool_name) || '';
    my ($groups, $used) = pool_special_devices($status_text, $pool_name);
    my @spares = @{ $groups->{spare} || [] };

    if ($in{'add_spare'}) {
        my @vdevs = selected_disks_from_form();
        if (!@vdevs) {
            print &ui_print_error(L("ERR_NO_DISKS_SELECTED"));
            return;
        }
        eval {
            zpool_add_spare($pool_name, @vdevs);
            log_info("Added spares to $pool_name: " . join(',', @vdevs));
            print &ui_print_success(L("SUCCESS_SPARE_ADDED", $pool_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SPARE_ADD_FAILED", $@));
        }
    }

    if ($in{'remove_spare'}) {
        my $dev = $in{'spare_device'} || '';
        if ($dev) {
            eval {
                zpool_remove($pool_name, $dev);
                log_info("Removed spare from $pool_name: $dev");
                print &ui_print_success(L("SUCCESS_SPARE_REMOVED", $pool_name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SPARE_REMOVE_FAILED", $@));
            }
        }
    }

    print &ui_subheading(L("SUB_POOL_SPARE", $pool_name));
    print_pool_action_help(
        what    => "Manages hot spare devices for automatic failover.",
        benefit => "Faster recovery when a disk fails.",
        risk    => "Spare assignment mistakes can waste or misallocate disks."
    );
    my @spare_heads = (L("COL_DEVICE"));
    my @spare_data  = map { [ &html_escape($_) ] } @spares;
    print &ui_columns_table(\@spare_heads, 100, \@spare_data, undef, 1, L("TABLE_SPARE_DEVICES"), L("VALUE_NONE"));

    print &ui_hr();
    print &ui_subheading(L("SUB_ADD_SPARE"));
    print "<p><small>Spare devices can be full disks or partition/slice entries.</small></p>";
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "spare");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("add_spare", 1);
    print &ui_table_start(L("TABLE_SELECT_SPARE"), "width=100%", 2);
    render_device_selector_rows(used => $used, name_prefix => 'disk_');
    print &ui_table_end();
    print &ui_form_end([ [ "add_spare", L("BTN_ADD_SPARE") ] ]);

    if (@spares) {
        print &ui_hr();
        print &ui_subheading(L("SUB_REMOVE_SPARE"));
        print &ui_form_start("advanced_pools.cgi", "post");
        print &ui_hidden("action", "spare");
        print &ui_hidden("pool", $pool_name);
        print &ui_hidden("remove_spare", 1);
        print &ui_table_start(L("TABLE_REMOVE_SPARE"), "width=100%", 2);
        print &ui_table_row(L("ROW_DEVICE"), &ui_select("spare_device", $spares[0], [ map { [ $_, $_ ] } @spares ]));
        print &ui_table_end();
        print &ui_form_end([ [ "remove_spare", L("BTN_REMOVE_SPARE") ] ]);
    }
}

sub action_properties {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);
    
    if ($in{'save_props'}) {
        foreach my $key (keys %in) {
            if ($key =~ /^prop_(.+)$/) {
                my $prop = $1;
                my $value = $in{$key};
                eval {
                    zpool_set_property($pool_name, $prop, $value);
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SET_PROPERTY_FAILED", "$prop: $@"));
                }
            }
        }
        print &ui_print_success(L("SUCCESS_PROPERTIES_UPDATED"));
    }
    
    my $props = zpool_properties($pool_name);
    my %prop_source;
    my $zpool_cmd = $zfsguru_lib::ZPOOL || '/sbin/zpool';
    my ($src_rc, $src_out, $src_err) = run_cmd($zpool_cmd, 'get', '-H', '-o', 'property,source', 'all', $pool_name);
    if ($src_rc == 0 && defined $src_out && $src_out =~ /\S/) {
        for my $ln (split /\n/, $src_out) {
            my ($k, $src) = split /\t+|\s+/, $ln, 2;
            next unless defined $k;
            $prop_source{$k} = defined($src) ? $src : '-';
        }
    }
    print &ui_subheading(L("SUB_POOL_PROPERTIES", $pool_name));
    print_pool_action_help(
        what    => "Edits pool-level properties.",
        benefit => "Central tuning of pool behavior and defaults.",
        risk    => "Unsafe values can impact compatibility/performance."
    );
    print &ui_form_start("advanced_pools.cgi", "post");
    print &ui_hidden("action", "props");
    print &ui_hidden("pool", $pool_name);
    print &ui_hidden("save_props", 1);
    
    print &ui_table_start(L("TABLE_PROPERTIES"), "width=100%", 2);
    for my $prop (sort keys %$props) {
        my $raw = $props->{$prop};
        my $value = ref($raw) eq 'HASH' ? ($raw->{value} // '') : (defined($raw) ? $raw : '');
        my $source = ref($raw) eq 'HASH' ? ($raw->{source} // '-') : ($prop_source{$prop} // '-');
        if ($prop eq 'ashift' && defined($value) && $value eq '0') {
            $value = '0 (auto/unset)';
        }
        print &ui_table_row($prop, &ui_textbox("prop_$prop", $value, 40) . " " . L("LABEL_FROM_SOURCE", $source));
    }
    print &ui_table_end();
    print &ui_form_end([ [ "save_props", L("BTN_SAVE_PROPERTIES") ] ]);
}

sub action_history {
    my $pool_name = $in{'pool'};
    die "Invalid pool name" unless is_pool_name($pool_name);
    
    my $history = zpool_history($pool_name, 50);
    print &ui_subheading(L("SUB_POOL_HISTORY", $pool_name));
    print_pool_action_help(
        what    => "Shows recent zpool administrative command history.",
        benefit => "Useful audit trail for troubleshooting changes.",
        risk    => "Read-only view; no direct risk."
    );
    my @heads = (L("COL_DATE"), L("COL_TIME"), L("COL_EVENT"));
    my @data;
    for my $e (@{ $history || [] }) {
        my ($d, $t, $event) = ('', '', '');
        if (ref($e) eq 'HASH') {
            $d = $e->{date} // '';
            $t = $e->{time} // '';
            $event = $e->{event} // '';
        } else {
            my $line = defined($e) ? $e : '';
            if ($line =~ /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s+(.*)$/) {
                ($d, $t, $event) = ($1, $2, $3);
            } else {
                $event = $line;
            }
        }
        push @data, [
            &html_escape($d),
            &html_escape($t),
            &html_escape($event),
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_HISTORY"), L("VALUE_NONE"));
}

sub candidate_block_devices_for_selection {
    my %seen;
    my @targets;
    my $disks = disk_list();
    for my $disk (@{ $disks || [] }) {
        next unless is_disk_name($disk);
        push @targets, "/dev/$disk";
        push @targets, glob("/dev/${disk}p*");
        push @targets, glob("/dev/${disk}s*");
    }
    @targets = grep { defined $_ && $_ =~ m{^/dev/} && !$seen{$_}++ } @targets;
    return \@targets;
}

sub render_device_selector_rows {
    my (%opt) = @_;
    my $used = $opt{used} || {};
    my $name_prefix = $opt{name_prefix} || 'disk_';
    my $targets = candidate_block_devices_for_selection();
    my $status_all = zpool_status() || '';
    my $parsed = parse_zpool_status($status_all);

    my %glabel_map;
    if (open(my $gl, '-|', 'glabel status')) {
        while (my $line = <$gl>) {
            chomp $line;
            if ($line =~ /^\s*(\S+)\s+\S+\s+(\S+)$/) {
                my ($label, $target) = ($1, $2);
                (my $t = $target) =~ s{^/dev/}{};
                $glabel_map{$label} = $t;
                $glabel_map{lc $label} = $t;
                $glabel_map{$t} = $t;
                $glabel_map{"/dev/$t"} = $t;
            }
        }
        close($gl);
    }

    my %member_to_pool;
    for my $p (@{ $parsed || [] }) {
        my $poolname = $p->{name} || '';
        for my $d (@{ $p->{devices} || [] }) {
            my $orig = $d->{name} || '';
            next unless $orig;
            (my $n = $orig) =~ s{^/dev/}{};
            my @variants = ($n, "/dev/$n", lc($n));
            if ($n =~ m{^(?:gpt/)?(.+)$}) {
                my $base = $1;
                push @variants, $base, "/dev/$base", "gpt/$base", "/dev/gpt/$base", lc($base), lc("gpt/$base");
            }
            if (exists $glabel_map{$n}) { push @variants, $glabel_map{$n}; }
            for my $v (@variants) {
                next unless defined $v && length $v;
                $member_to_pool{$v} = $poolname;
            }
        }
    }

    my %boot_parts;
    my %seen_parent;
    for my $dev (@$targets) {
        (my $name = $dev) =~ s{^/dev/}{};
        next unless $name =~ /^([A-Za-z0-9:_\-\.]+)\d*$/;
        my $parent = $name;
        if ($name =~ /^([A-Za-z0-9:_\-\.]+)p\d+$/) {
            $parent = $1;
        } elsif ($name =~ /^([A-Za-z0-9:_\-\.]+)s\d+$/) {
            $parent = $1;
        }
        next if $seen_parent{$parent}++;
        if (open(my $gp, '-|', "gpart show $parent 2>/dev/null")) {
            while (my $line = <$gp>) {
                if ($line =~ /^\s+\d+\s+(\d+)\s+(\d+)\s+(\S+)/) {
                    my ($size_blocks, $idx, $ptype) = ($1, $2, $3);
                    next if $ptype eq '-' || $ptype eq 'free';
                    if ($ptype =~ /\b(freebsd-boot|efi|bios-boot|netbsd-boot|openbsd-boot|apple-boot)\b/i
                        || ($idx == 1 && $size_blocks <= 1024)) {
                        $boot_parts{$parent . 'p' . $idx} = $ptype;
                    }
                }
            }
            close($gp);
        }
    }

    my @item_html;
    my $row_i = 0;
    for my $dev (@$targets) {
        $row_i++;
        my $name = $dev; $name =~ s{^/dev/}{};
        my $state = L("VALUE_AVAILABLE");
        my @notes;
        my $disabled = 0;

        my $pool_owner = $member_to_pool{$name} || $member_to_pool{$dev} || '';
        if (!$pool_owner) {
            for my $k (keys %member_to_pool) {
                next unless defined $k && length $k;
                if ($k =~ /^\Q$name\E(?:p|s)\d+$/i) {
                    $pool_owner = $member_to_pool{$k} || '';
                    last;
                }
            }
        }

        if ($pool_owner) {
            $state = L("VALUE_IN_USE");
            push @notes, "Member of pool: $pool_owner";
            $disabled = 1;
        }
        my $mnt = device_mountpoints($dev);
        if ($mnt && ref($mnt) eq 'ARRAY' && @$mnt) {
            push @notes, L("MSG_DEVICE_MOUNTED", join(', ', @$mnt));
        }
        if (swap_is_active($dev) || swap_is_active($name)) {
            $state = L("VALUE_IN_USE");
            push @notes, "Active swap device";
            $disabled = 1;
        }
        if (exists $boot_parts{$name}) {
            $state = L("VALUE_RESERVED");
            my $ptype = $boot_parts{$name} || 'boot';
            push @notes, L("MSG_ADD_VDEV_BOOT_PARTITION", $ptype);
            $disabled = 1;
        }

        if (($used->{$name} || $used->{"/dev/$name"} || $used->{$dev}) && !$disabled) {
            $state = L("VALUE_IN_USE");
            push @notes, "Already used by this pool topology";
            $disabled = 1;
        }

        my $cb = $disabled
            ? "<input type='checkbox' disabled>"
            : "<input type='checkbox' name='" . &html_escape($name_prefix . $name) . "' value='1'>";

        my $info = @notes ? join(' | ', @notes) : '-';
        my $bg = ($row_i % 2) ? '#f7f9fc' : '#eef3f9';
        push @item_html,
            "<div style='break-inside:avoid; margin:0 0 6px 0; background:$bg; border:1px solid #dde3ec; border-radius:4px; padding:4px 6px;'>" .
            "<label style='display:inline-flex; align-items:center; gap:6px; max-width:100%;'>" .
            $cb .
            "<span style='font-weight:600;'>" . &html_escape($name) . "</span>" .
            "<span style='color:#666;'>[" . &html_escape($state) . "]</span>" .
            "<span style='color:#333; font-size:12px;'>" . &html_escape($info) . "</span>" .
            "</label>" .
            "</div>";
    }
    my $columns_html = "<div style='column-count:2; column-gap:22px;'>" . join('', @item_html) . "</div>";
    print &ui_table_row("", $columns_html);
}

sub selected_disks_from_form {
    return selected_vdevs_from_form();
}

sub pool_special_devices {
    my ($status_text, $pool_name) = @_;
    my %groups = (cache => [], slog => [], spare => []);
    my %used;
    my $section = '';
    my $in_config = 0;
    for my $line (split /\n/, ($status_text || '')) {
        if ($line =~ /^\s*config:/) {
            $in_config = 1;
            next;
        }
        next unless $in_config;
        if ($line =~ /^\s*(cache|logs|spares)\b/) {
            $section = $1;
            next;
        }
        next if $line =~ /^\s*$/;
        if ($line =~ /^\s+(\S+)\s+(ONLINE|OFFLINE|DEGRADED|FAULTED|REMOVED|UNAVAIL|AVAIL|INUSE)\b/) {
            my $dev = $1;
            next if $dev eq $pool_name;
            next if $dev =~ /^(mirror|raidz\d*|spares|logs|cache|special|dedup|replacing)/;
            $used{$dev} = 1;
            if ($section eq 'cache') {
                push @{ $groups{cache} }, $dev;
            } elsif ($section eq 'logs') {
                push @{ $groups{slog} }, $dev;
            } elsif ($section eq 'spares') {
                push @{ $groups{spare} }, $dev;
            }
        }
    }
    return (\%groups, \%used);
}

sub pool_benchmark_job {
    my (%opt) = @_;
    my $pool = $opt{pool} || '';
    my $size_mib = $opt{size_mib} || 0;
    my $tests = $opt{tests} || {};

    die "Invalid pool name" unless is_pool_name($pool);
    die "Invalid test size" unless defined $size_mib && $size_mib =~ /^\d+$/ && $size_mib > 0;
    die "Invalid tests" unless ref($tests) eq 'HASH';

    my $testfs = $pool . '/zfsguru-performance-test-' . time() . '-' . $$;
    my $testfilename = 'zfsguru_benchmark.000';
    my $need_bytes = $size_mib * 1024 * 1024;
    my $needs_fs_tests = ($tests->{normal} || $tests->{lzjb} || $tests->{gzip}) ? 1 : 0;

    print STDOUT "Pool: $pool\n";
    print STDOUT "Test filesystem: $testfs\n";
    print STDOUT "Test size: ${size_mib} MiB\n";
    print STDOUT "Tests: " . join(', ',
        ($tests->{normal} ? 'normal' : ()),
        ($tests->{lzjb} ? 'lzjb' : ()),
        ($tests->{gzip} ? 'gzip' : ()),
        ($tests->{bandwidth} ? 'bandwidth' : ()),
    ) . "\n";
    print STDOUT "\n";

    if ($needs_fs_tests) {
        my $avail = zfs_get_prop_value_bytes($pool, 'available');
        if (defined $avail && $avail =~ /^\d+$/ && $avail < $need_bytes) {
            die "Not enough available space on $pool (need $need_bytes bytes, available $avail bytes)";
        }

    }

    my $created = 0;
    my %results;
    my $mountpoint = '';
    my $testfile = '';

    my $cleanup = sub {
        if ($testfile && -e $testfile) {
            eval { unlink $testfile; };
        }
        if ($created) {
            eval { zfs_destroy($testfs); };
        }
    };

    eval {
        if ($needs_fs_tests) {
            zfs_create($testfs, '-o', 'dedup=off');
            $created = 1;

            $mountpoint = zfs_get_prop_value($testfs, 'mountpoint');
            die "Invalid mountpoint for $testfs" unless defined $mountpoint && $mountpoint =~ m{^/};
            $testfile = $mountpoint . '/' . $testfilename;

            if ($tests->{normal}) {
                $results{normal} = _pool_bench_run_fs_test($testfs, $testfile, $size_mib, 'off');
            }
            if ($tests->{lzjb}) {
                $results{lzjb} = _pool_bench_run_fs_test($testfs, $testfile, $size_mib, 'lzjb');
            }
            if ($tests->{gzip}) {
                $results{gzip} = _pool_bench_run_fs_test($testfs, $testfile, $size_mib, 'gzip');
            }
        }
        if ($tests->{bandwidth}) {
            my ($bps, $line) = _pool_bench_dd('dd if=/dev/zero of=/dev/null', [ $zfsguru_lib::DD, 'if=/dev/zero', 'of=/dev/null', 'bs=1m', "count=$size_mib" ]);
            $results{bandwidth} = {
                bps  => $bps,
                line => $line,
            };
        }

        1;
    } or do {
        my $err = $@;
        $cleanup->();
        die $err;
    };

    $cleanup->();

    print STDOUT "\nSummary\n";
    print STDOUT "=======\n";
    for my $k (qw(normal lzjb gzip bandwidth)) {
        next unless $results{$k};
        if ($k eq 'bandwidth') {
            my $bps = $results{$k}{bps};
            print STDOUT "$k: " . (_pool_bench_bps_human($bps) || '') . "\n";
            next;
        }
        my $w = $results{$k}{write_bps};
        my $r = $results{$k}{read_bps};
        print STDOUT "$k write: " . (_pool_bench_bps_human($w) || '') . "\n";
        print STDOUT "$k read : " . (_pool_bench_bps_human($r) || '') . "\n";
    }
}

sub _pool_bench_run_fs_test {
    my ($dataset, $testfile, $size_mib, $compression) = @_;
    die "Invalid dataset" unless is_dataset_name($dataset);
    die "Invalid testfile" unless defined $testfile && $testfile =~ m{^/};
    die "Invalid size" unless defined $size_mib && $size_mib =~ /^\d+$/ && $size_mib > 0;
    die "Invalid compression" unless defined $compression && $compression =~ /^[A-Za-z0-9_.\-]+$/;

    print STDOUT "\n=== compression=$compression ===\n";
    zfs_set($dataset, 'compression', $compression);

    # Best-effort remove any previous file.
    if (-e $testfile) {
        eval { unlink $testfile; };
    }

    my ($wbps, $wline) = _pool_bench_dd(
        "dd write ($compression)",
        [ $zfsguru_lib::DD, 'if=/dev/zero', "of=$testfile", 'bs=1m', "count=$size_mib" ]
    );
    _pool_bench_cooldown();

    my ($rbps, $rline) = _pool_bench_dd(
        "dd read ($compression)",
        [ $zfsguru_lib::DD, "if=$testfile", 'of=/dev/null', 'bs=1m' ]
    );

    if (-e $testfile) {
        unlink $testfile or warn "unlink failed: $!";
    }
    _pool_bench_cooldown();

    return {
        write_bps  => $wbps,
        read_bps   => $rbps,
        write_line => $wline,
        read_line  => $rline,
    };
}

sub _pool_bench_cooldown {
    # Reduce cache contamination between phases. Keep it simple and predictable.
    eval { system('/bin/sync'); };
    sleep 10;
}

sub _pool_bench_dd {
    my ($label, $cmd) = @_;
    die "Invalid command" unless ref($cmd) eq 'ARRAY' && @$cmd;

    my @c = @$cmd;
    print STDOUT ">> $label\n";
    print STDOUT ">> " . join(' ', @c) . "\n";
    my ($rc, $out, $err) = run_cmd(@c);
    print STDOUT $out if defined $out && length $out;
    print STDOUT $err if defined $err && length $err;
    die "Command failed rc=$rc: $label" if $rc != 0;

    my $all = ($out || '') . ($err || '');
    my @lines = grep { /\S/ } split(/\n/, $all);
    my $last = @lines ? $lines[-1] : '';
    my $bps = _pool_bench_parse_dd_bps($last);
    if (defined $bps && $bps =~ /^\d+$/) {
        print STDOUT ">> speed: " . _pool_bench_bps_human($bps) . "\n";
    }
    print STDOUT "\n";
    return ($bps, $last);
}

sub _pool_bench_parse_dd_bps {
    my ($line) = @_;
    return undef unless defined $line;
    my ($bps) = ($line =~ /\((\d+)\s+bytes\/sec\)/);
    return $bps;
}

sub _pool_bench_bps_human {
    my ($bps) = @_;
    return '' unless defined $bps && $bps =~ /^\d+$/;
    my $mib = $bps / (1024 * 1024);
    if ($mib >= 1024) {
        my $gib = $mib / 1024;
        my $s = sprintf("%.1f", $gib);
        $s =~ s/\.0$//;
        return $s . " GiB/s";
    }
    my $s = sprintf("%.1f", $mib);
    $s =~ s/\.0$//;
    return $s . " MiB/s";
}

sub _pool_bench_human_to_mib {
    my ($txt) = @_;
    return undef unless defined $txt;
    $txt =~ s/^\s+|\s+$//g;
    return undef if $txt eq '';
    if ($txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*([KMG])iB\/s$/i) {
        my ($v, $u) = ($1 + 0, uc($2));
        return $v / 1024 if $u eq 'K';
        return $v if $u eq 'M';
        return $v * 1024 if $u eq 'G';
    }
    if ($txt =~ /^([0-9]+(?:\.[0-9]+)?)\s*B\/s$/i) {
        return ($1 + 0) / (1024 * 1024);
    }
    return undef;
}

sub _pool_bench_label {
    my ($test, $kind) = @_;
    my %names = (
        normal    => 'Normal',
        lzjb      => 'LZJB',
        gzip      => 'GZIP',
        bandwidth => 'Bandwidth',
    );
    my $base = $names{$test} || $test;
    return $base if !defined($kind) || $kind eq '';
    return $base . " " . ucfirst($kind);
}

sub parse_pool_benchmark_results {
    my ($txt) = @_;
    return ([], {}) unless defined $txt && length $txt;
    my %found;
    my %dur_secs;
    my $current_key = '';
    my $test_size = '';
    my @selected_tests;
    my %selected_seen;
    my %test_label = (
        normal    => L("OPT_POOL_BENCH_NORMAL"),
        lzjb      => L("OPT_POOL_BENCH_LZJB"),
        gzip      => L("OPT_POOL_BENCH_GZIP"),
        bandwidth => L("OPT_POOL_BENCH_BANDWIDTH"),
    );
    my %compression_to_test = (
        off  => 'normal',
        lzjb => 'lzjb',
        gzip => 'gzip',
    );
    for my $line (split /\n/, $txt) {
        $line =~ s/\r$//;
        my $raw_line = $line;
        $line =~ s/^\[[0-9:\-\s]+\]\s*//;
        $line =~ s/^\s+|\s+$//g;
        next if $line eq '';
        if ($line =~ /^Test size:\s*(.+)$/i) {
            $test_size = $1;
            next;
        }
        if ($line =~ /^Tests:\s*(.+)$/i) {
            my $tests = $1;
            for my $t (split /\s*,\s*/, $tests) {
                my $k = lc($t // '');
                next unless $k =~ /^(normal|lzjb|gzip|bandwidth)$/;
                next if $selected_seen{$k}++;
                push @selected_tests, ($test_label{$k} || $k);
            }
            next;
        }
        if ($line =~ /^>>\s*dd\s+(write|read)\s+\(([^)]+)\)\s*$/i) {
            my ($kind, $comp) = (lc($1), lc($2));
            my $test = $compression_to_test{$comp} || $comp;
            $current_key = $test . ':' . $kind;
            next;
        }
        if ($line =~ /^>>\s*dd\s+if=\/dev\/zero\s+of=\/dev\/null/i) {
            $current_key = 'bandwidth';
            next;
        }
        if ($line =~ /^>>\s*speed:\s*(.+)$/i) {
            my $speed = $1;
            if ($current_key ne '' && !exists $found{$current_key}) {
                $found{$current_key} = $speed;
            }
            next;
        }
        if ($line =~ /^\d+\s+bytes transferred in\s+([0-9]+(?:\.[0-9]+)?)\s+secs?/i) {
            my $secs = $1 + 0;
            if ($current_key ne '' && !exists $dur_secs{$current_key}) {
                $dur_secs{$current_key} = $secs;
            }
            next;
        }
        if ($line =~ /^(normal|lzjb|gzip)\s+(write|read)\s*:\s*(.+)$/i) {
            $found{lc($1) . ':' . lc($2)} = $3;
            next;
        }
        if ($line =~ /^bandwidth\s*:\s*(.+)$/i) {
            $found{'bandwidth'} = $1;
            next;
        }
        # Keep parser resilient if timestamps are attached to dd/speed lines by wrappers.
        if ($raw_line =~ />>\s*speed:\s*(.+)$/i && $current_key ne '' && !exists $found{$current_key}) {
            $found{$current_key} = $1;
            next;
        }
    }

    my @order = (
        [ 'normal', 'write' ],
        [ 'normal', 'read' ],
        [ 'lzjb', 'write' ],
        [ 'lzjb', 'read' ],
        [ 'gzip', 'write' ],
        [ 'gzip', 'read' ],
        [ 'bandwidth', '' ],
    );
    my @rows;
    for my $o (@order) {
        my ($test, $kind) = @$o;
        my $key = $kind ? "$test:$kind" : $test;
        next unless exists $found{$key};
        my $throughput = $found{$key};
        my $mib = _pool_bench_human_to_mib($throughput);
        $mib = 0 unless defined $mib && $mib >= 0;
        my $secs = exists $dur_secs{$key} ? $dur_secs{$key} : undef;
        my $color = $test eq 'bandwidth' ? '#5cb85c'
                  : $kind eq 'write'      ? '#f0ad4e'
                  :                          '#0275d8';
        push @rows, {
            label      => _pool_bench_label($test, $kind),
            throughput => $throughput,
            duration   => _pool_bench_secs_human($secs),
            mib        => $mib,
            color      => $color,
        };
    }
    return (\@rows, { test_size => $test_size, selected_tests => \@selected_tests });
}

sub _pool_bench_secs_human {
    my ($secs) = @_;
    return '' unless defined $secs && $secs =~ /^[0-9]+(?:\.[0-9]+)?$/;
    return sprintf("%.3f s", $secs + 0);
}

sub render_pool_benchmark_chart {
    my ($rows) = @_;
    return '' unless ref($rows) eq 'ARRAY' && @$rows;
    my $max_mib = 0;
    for my $r (@$rows) {
        my $v = $r->{mib};
        $max_mib = $v if defined $v && $v > $max_mib;
    }
    $max_mib = 1 if $max_mib <= 0;

    my $has_duration = 0;
    for my $r (@$rows) {
        if (defined $r->{duration} && $r->{duration} ne '') {
            $has_duration = 1;
            last;
        }
    }
    my $cols = $has_duration
        ? "220px 1fr 110px 120px"
        : "220px 1fr 110px";
    my $html = "<div style='max-width:980px;border:1px solid #d7dbe0;border-radius:6px;padding:12px;background:#f7fafc'>";
    $html .= "<div style='display:grid;grid-template-columns:$cols;gap:10px;align-items:center;margin:0 0 8px 0;font-weight:600;color:#5f6b7a'>";
    $html .= "<div>" . &html_escape(L("COL_BENCH_METRIC")) . "</div>";
    $html .= "<div></div>";
    $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_THROUGHPUT")) . "</div>";
    if ($has_duration) {
        $html .= "<div style='text-align:right'>" . &html_escape(L("COL_BENCH_DURATION")) . "</div>";
    }
    $html .= "</div>";
    for my $r (@$rows) {
        my $v = $r->{mib} || 0;
        my $pct = int(($v / $max_mib) * 100);
        $pct = 1 if $v > 0 && $pct < 1;
        my $label = &html_escape($r->{label} || '');
        my $thr = &html_escape($r->{throughput} || '');
        my $dur = &html_escape($r->{duration} || '');
        my $color = $r->{color} || '#0275d8';
        my $title = sprintf("%.1f MiB/s", $v);
        $html .= "<div style='display:grid;grid-template-columns:$cols;gap:10px;align-items:center;margin:6px 0'>";
        $html .= "<div>$label</div>";
        $html .= "<div style='height:16px;background:#e7edf3;border-radius:3px;overflow:hidden'>"
              .  "<div title='" . &html_escape($title) . "' style='height:100%;width:${pct}%;background:$color'></div>"
              .  "</div>";
        $html .= "<div style='text-align:right;font-weight:600'>$thr</div>";
        if ($has_duration) {
            $html .= "<div style='text-align:right;color:#5f6b7a'>" . ($dur ne '' ? $dur : '-') . "</div>";
        }
        $html .= "</div>";
    }
    $html .= "</div>";
    return $html;
}

1;
