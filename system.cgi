#!/usr/bin/env perl

package main;

use strict;
use warnings;
use POSIX qw(strftime);
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

our %config;

if ($ENV{'CONTENT_TYPE'} && $ENV{'CONTENT_TYPE'} =~ /^multipart\/form-data/i) {
    zfsguru_readparse_mime();
} else {
    zfsguru_readparse();
}
zfsguru_init('en');

my $action = $in{'action'} || 'preferences';

# Archive download needs to happen before HTML headers are printed.
if ($action eq 'migration' && ($in{'mig_do'} || '') eq 'download') {
    action_migration_download();
    exit 0;
}

zfsguru_page_header(title_key => "TITLE_SYSTEM");

eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('system'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'system'));
    zfsguru_page_footer();
    exit 0;
}

my $update_ui_enabled = $config{'enable_system_update_ui'} ? 1 : 0;
my $update_ui_blocked = 0;
if ($action eq 'update' && !$update_ui_enabled) {
    $update_ui_blocked = 1;
    $action = 'preferences';
}
my @tabs_list = (
    [ 'preferences', 'TAB_SYS_PREFERENCES' ],
    [ 'tuning',      'TAB_SYS_TUNING' ],
    [ 'booting',     'TAB_SYS_BOOTING' ],
    [ 'migration',   'TAB_SYS_MIGRATION' ],
    [ 'cli',         'TAB_SYS_CLI' ],
);
push @tabs_list, [ 'update',   'TAB_SYS_UPDATE' ]   if $update_ui_enabled;
push @tabs_list, [ 'shutdown', 'TAB_SYS_SHUTDOWN' ];

print zfsguru_print_tabs(
    script => 'system.cgi',
    active => $action,
    tabs   => \@tabs_list,
);

print &ui_alert(L("ERR_SYS_UPDATE_UI_DISABLED"), 'warning') if $update_ui_blocked;

if ($action eq 'preferences') {
    action_preferences();
} elsif ($action eq 'tuning') {
    action_tuning();
} elsif ($action eq 'booting') {
    action_booting();
} elsif ($action eq 'migration') {
    action_migration();
} elsif ($action eq 'cli') {
    action_cli();
} elsif ($action eq 'update') {
    action_update();
} elsif ($action eq 'shutdown') {
    action_shutdown();
}

my $back_url = 'index.cgi';
if ($action ne 'preferences') {
    $back_url = 'system.cgi?action=preferences';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_preferences {
    my $prefs_tab = $in{'prefs_tab'} || 'general';
    my %valid_tabs = map { $_ => 1 } qw(general monitoring safety config);
    $prefs_tab = 'general' unless $valid_tabs{$prefs_tab};
    my %managed_pref_keys = map { $_ => 1 } prefcfg_managed_pref_keys();

    if ($in{'save_prefs_group'}) {
        my $group = $in{'save_prefs_group'} || '';
        eval {
            if ($group eq 'general') {
                my %updates = (
                    advanced_mode           => ($in{'advanced_mode'} ? 1 : 0),
                    booting_expert_mode     => ($in{'booting_expert_mode'} ? 1 : 0),
                    enable_smart_monitoring => ($in{'enable_smart_monitoring'} ? 1 : 0),
                    enable_benchmarking     => ($in{'enable_benchmarking'} ? 1 : 0),
                    enable_system_update_ui => ($in{'enable_system_update_ui'} ? 1 : 0),
                );
                my $backup = prefcfg_apply_updates(\%updates);
                print &ui_print_success(L("SUCCESS_SYSTEM_PREFS_SAVED"));
                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-')) if $backup;
            }
            elsif ($group eq 'monitoring') {
                my $warn = defined($in{'monitor_pool_capacity_threshold'}) ? $in{'monitor_pool_capacity_threshold'} : 80;
                my $crit = defined($in{'monitor_alert_high_capacity'}) ? $in{'monitor_alert_high_capacity'} : 90;
                my $twarn = defined($in{'monitor_disk_temperature_warning'}) ? $in{'monitor_disk_temperature_warning'} : 45;
                my $tcrit = defined($in{'monitor_disk_temperature_critical'}) ? $in{'monitor_disk_temperature_critical'} : 55;
                my $log_level = $in{'log_level'} || 'info';
                my $auto_refresh = $in{'auto_refresh'} ? 1 : 0;
                my $auto_refresh_interval = defined($in{'auto_refresh_interval'}) ? $in{'auto_refresh_interval'} : 30;
                my $animation_effects = $in{'animation_effects'} ? 1 : 0;

                die L("ERR_PREFS_INT_RANGE", L("ROW_POOL_CAPACITY_WARN"), 0, 100) unless $warn =~ /^\d+$/ && $warn >= 0 && $warn <= 100;
                die L("ERR_PREFS_INT_RANGE", L("ROW_POOL_CAPACITY_CRIT"), 0, 100) unless $crit =~ /^\d+$/ && $crit >= 0 && $crit <= 100;
                die L("ERR_PREFS_INT_RANGE", L("ROW_MONITOR_DISK_TEMP_WARN"), 0, 200) unless $twarn =~ /^\d+$/ && $twarn >= 0 && $twarn <= 200;
                die L("ERR_PREFS_INT_RANGE", L("ROW_MONITOR_DISK_TEMP_CRIT"), 0, 200) unless $tcrit =~ /^\d+$/ && $tcrit >= 0 && $tcrit <= 200;
                die L("ERR_PREFS_INT_RANGE", L("ROW_AUTO_REFRESH_INTERVAL"), 0, 86400) unless $auto_refresh_interval =~ /^\d+$/ && $auto_refresh_interval >= 0 && $auto_refresh_interval <= 86400;
                die L("ERR_PREFS_LOG_LEVEL") unless $log_level =~ /^(?:debug|info|warn|warning|error)$/i;

                my %updates = (
                    monitor_pool_capacity_threshold   => $warn,
                    monitor_alert_high_capacity       => $crit,
                    monitor_disk_temperature_warning  => $twarn,
                    monitor_disk_temperature_critical => $tcrit,
                    log_level                         => lc($log_level),
                    auto_refresh                      => $auto_refresh,
                    auto_refresh_interval             => $auto_refresh_interval,
                    animation_effects                 => $animation_effects,
                );
                my $backup = prefcfg_apply_updates(\%updates);
                print &ui_print_success(L("SUCCESS_SYSTEM_PREFS_SAVED"));
                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-')) if $backup;
            }
            elsif ($group eq 'safety') {
                my $ata_mode = $in{'ata_secure_erase_mode'} || 'normal';
                $ata_mode = 'normal' unless $ata_mode eq 'enhanced';
                my $ata_pass = $in{'ata_secure_erase_pass'} // '';
                $ata_pass =~ s/[\r\n]//g;
                my %updates = (
                    require_confirmation_for_pool_create => ($in{'require_confirmation_for_pool_create'} ? 1 : 0),
                    require_confirmation_for_disk_format => ($in{'require_confirmation_for_disk_format'} ? 1 : 0),
                    require_confirmation_for_pool_export => ($in{'require_confirmation_for_pool_export'} ? 1 : 0),
                    ata_secure_erase_mode                => $ata_mode,
                    ata_secure_erase_pass                => $ata_pass,
                );
                my $backup = prefcfg_apply_updates(\%updates);
                print &ui_print_success(L("SUCCESS_SYSTEM_PREFS_SAVED"));
                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-')) if $backup;
            }
            elsif ($group eq 'config') {
                my $cfg_file = prefcfg_file_path();
                my $raw = read_file_text($cfg_file);
                my ($order, $existing) = prefcfg_parse_config_kv($raw);
                my %newvals;
                my @ordered_names;

                my $count = int($in{'cfg_count'} || 0);
                for my $i (0 .. $count - 1) {
                    my $name = $in{"cfg_name_$i"};
                    next unless defined $name;
                    $name =~ s/^\s+|\s+$//g;
                    next unless $name =~ /^[A-Za-z0-9_]+$/;
                    my $val = defined($in{"cfg_val_$i"}) ? $in{"cfg_val_$i"} : '';
                    $val =~ s/\r//g;
                    $val =~ s/\n/ /g;
                    $newvals{$name} = $val;
                    push @ordered_names, $name;
                }

                my $extra = defined($in{'cfg_new_entries'}) ? $in{'cfg_new_entries'} : '';
                for my $line (split /\n/, $extra) {
                    $line =~ s/\r//g;
                    $line =~ s/^\s+|\s+$//g;
                    next unless length $line;
                    next if $line =~ /^\s*#/;
                    next unless $line =~ /^([A-Za-z0-9_]+)\s*=\s*(.*)$/;
                    my ($k, $v) = ($1, $2);
                    $v =~ s/\r//g;
                    $v =~ s/\n/ /g;
                    if (!exists $newvals{$k}) {
                        push @ordered_names, $k;
                    }
                    $newvals{$k} = $v;
                }

                # Keys managed by dedicated Preferences tabs are not editable here.
                for my $mk (keys %managed_pref_keys) {
                    delete $newvals{$mk};
                }
                @ordered_names = grep { !$managed_pref_keys{$_} } @ordered_names;

                my @val_errors = prefcfg_validate_config_values(\%newvals);
                die join("\n", @val_errors) if @val_errors;

                my $new_raw = prefcfg_rewrite_config_preserve_layout($raw, \%newvals, \@ordered_names);
                my $backup = write_file_with_backup($cfg_file, $new_raw);
                for my $k (keys %newvals) {
                    $config{$k} = $newvals{$k};
                }
                &save_module_config(\%config);
                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
                print &ui_print_success(L("SUCCESS_MODULE_CONFIG_SAVED"));
            }
        };
        if ($@) {
            print &ui_print_error(L("ERR_SYSTEM_PREFS_SAVE_FAILED", $@));
        }
    }

    print &ui_subheading(L("SUB_SYS_PREFERENCES"));
    print "<p>" . L("MSG_SYS_PREFS_GROUPED_NOTE") . "</p>";

    my @pref_tabs = (
        [ 'general',    'TAB_SYS_PREFS_GENERAL' ],
        [ 'monitoring', 'TAB_SYS_PREFS_MONITORING' ],
        [ 'safety',     'TAB_SYS_PREFS_SAFETY' ],
        [ 'config',     'TAB_SYS_PREFS_CONFIG' ],
    );
    print zfsguru_print_tabs(
        script => 'system.cgi?action=preferences',
        active => $prefs_tab,
        tabs   => \@pref_tabs,
        param  => 'prefs_tab',
    );

    if ($prefs_tab eq 'general') {
        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "preferences");
        print &ui_hidden("prefs_tab", "general");
        print &ui_hidden("save_prefs_group", "general");
        print &ui_table_start(L("TABLE_SYSTEM_PREFS_GENERAL"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_ADVANCED_MODE"),
            &ui_checkbox("advanced_mode", 1, L("OPT_ENABLED"), ($config{'advanced_mode'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_BOOTING_EXPERT_MODE"),
            &ui_checkbox("booting_expert_mode", 1, L("OPT_ENABLED"), ($config{'booting_expert_mode'} || 0) ? 1 : 0) .
            "<br><small>" . L("HINT_BOOTING_EXPERT_MODE") . "</small>"
        );
        print &ui_table_row(
            L("ROW_ENABLE_SMART_MONITORING"),
            &ui_checkbox("enable_smart_monitoring", 1, L("OPT_ENABLED"), ($config{'enable_smart_monitoring'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_ENABLE_BENCHMARKING"),
            &ui_checkbox("enable_benchmarking", 1, L("OPT_ENABLED"), ($config{'enable_benchmarking'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_ENABLE_SYSTEM_UPDATE_UI"),
            &ui_checkbox("enable_system_update_ui", 1, L("OPT_ENABLED"), ($config{'enable_system_update_ui'} || 0) ? 1 : 0) .
            "<br><small>" . L("HINT_ENABLE_SYSTEM_UPDATE_UI") . "</small>"
        );
        print &ui_table_end();
        print &ui_form_end([ [ "save_prefs_group", L("BTN_SAVE_SYSTEM_PREFS") ] ]);
        return;
    }

    if ($prefs_tab eq 'monitoring') {
        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "preferences");
        print &ui_hidden("prefs_tab", "monitoring");
        print &ui_hidden("save_prefs_group", "monitoring");
        print &ui_table_start(L("TABLE_SYSTEM_PREFS_MONITORING"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_POOL_CAPACITY_WARN"),
            &ui_textbox("monitor_pool_capacity_threshold", (defined $config{'monitor_pool_capacity_threshold'} ? $config{'monitor_pool_capacity_threshold'} : 80), 6) . " %"
        );
        print &ui_table_row(
            L("ROW_POOL_CAPACITY_CRIT"),
            &ui_textbox("monitor_alert_high_capacity", (defined $config{'monitor_alert_high_capacity'} ? $config{'monitor_alert_high_capacity'} : 90), 6) . " %"
        );
        print &ui_table_row(
            L("ROW_MONITOR_DISK_TEMP_WARN"),
            &ui_textbox("monitor_disk_temperature_warning", (defined $config{'monitor_disk_temperature_warning'} ? $config{'monitor_disk_temperature_warning'} : 45), 6) . " C"
        );
        print &ui_table_row(
            L("ROW_MONITOR_DISK_TEMP_CRIT"),
            &ui_textbox("monitor_disk_temperature_critical", (defined $config{'monitor_disk_temperature_critical'} ? $config{'monitor_disk_temperature_critical'} : 55), 6) . " C"
        );
        print &ui_table_row(
            L("ROW_LOG_LEVEL"),
            &ui_select("log_level", ($config{'log_level'} || 'info'), [
                [ "debug", "debug" ],
                [ "info", "info" ],
                [ "warn", "warn" ],
                [ "error", "error" ],
            ])
        );
        print &ui_table_row(
            L("ROW_AUTO_REFRESH"),
            &ui_checkbox("auto_refresh", 1, L("OPT_ENABLED"), ($config{'auto_refresh'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_AUTO_REFRESH_INTERVAL"),
            &ui_textbox("auto_refresh_interval", (defined $config{'auto_refresh_interval'} ? $config{'auto_refresh_interval'} : 30), 8) .
            " s<br><small>" . L("HINT_AUTO_REFRESH_INTERVAL") . "</small>"
        );
        print &ui_table_row(
            L("ROW_ANIMATION_EFFECTS"),
            &ui_checkbox("animation_effects", 1, L("OPT_ENABLED"), ($config{'animation_effects'} || 0) ? 1 : 0)
        );
        print &ui_table_end();
        print &ui_form_end([ [ "save_prefs_group", L("BTN_SAVE_SYSTEM_PREFS") ] ]);
        return;
    }

    if ($prefs_tab eq 'safety') {
        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "preferences");
        print &ui_hidden("prefs_tab", "safety");
        print &ui_hidden("save_prefs_group", "safety");
        print &ui_table_start(L("TABLE_SYSTEM_PREFS_SAFETY"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_CONFIRM_POOL_CREATE"),
            &ui_checkbox("require_confirmation_for_pool_create", 1, L("OPT_ENABLED"), ($config{'require_confirmation_for_pool_create'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_CONFIRM_DISK_FORMAT"),
            &ui_checkbox("require_confirmation_for_disk_format", 1, L("OPT_ENABLED"), ($config{'require_confirmation_for_disk_format'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_CONFIRM_POOL_EXPORT"),
            &ui_checkbox("require_confirmation_for_pool_export", 1, L("OPT_ENABLED"), ($config{'require_confirmation_for_pool_export'} || 0) ? 1 : 0)
        );
        print &ui_table_row(
            L("ROW_ATA_SECURE_ERASE_MODE"),
            &ui_select("ata_secure_erase_mode", ($config{'ata_secure_erase_mode'} || 'normal'), [
                [ "normal", L("OPT_ATA_MODE_NORMAL") ],
                [ "enhanced", L("OPT_ATA_MODE_ENHANCED") ],
            ])
        );
        print &ui_table_row(
            L("ROW_ATA_SECURE_ERASE_PASS"),
            &ui_password("ata_secure_erase_pass", ($config{'ata_secure_erase_pass'} || ''), 30)
        );
        print &ui_table_row(
            L("ROW_ATA_SECURE_ERASE_NOTE"),
            L("MSG_ATA_SECURE_ERASE_NOTE")
        );
        print &ui_table_end();
        print &ui_form_end([ [ "save_prefs_group", L("BTN_SAVE_SYSTEM_PREFS") ] ]);
        return;
    }

    # config tab: full config.txt editor
    my $cfg_file = prefcfg_file_path();
    if (!-r $cfg_file) {
        print &ui_print_error(L("ERR_MODULE_CONFIG_FILE_UNREADABLE", $cfg_file));
        return;
    }

    my $raw = read_file_text($cfg_file);
    my ($order, $kv) = prefcfg_parse_config_kv($raw);
    my $groups = prefcfg_group_config_keys($order);

    print &ui_subheading(L("SUB_SYS_PREFS_CONFIG_KEYS"));
    print "<p>" . L("MSG_SYS_PREFS_PRECEDENCE") . "</p>";
    my @managed_list = sort keys %managed_pref_keys;
    if (@managed_list) {
        print &ui_alert(L("MSG_SYS_PREFS_CONFIG_MANAGED_KEYS", join(", ", @managed_list)), 'info');
    }
    print "<p><label for='cfg_search'><b>" . L("ROW_SEARCH_KEYS") . "</b></label> " .
          "<input type='text' id='cfg_search' style='min-width:300px' placeholder='" . &html_escape(L("PH_SEARCH_KEYS")) . "'> " .
          "<small>" . L("HINT_SEARCH_KEYS") . "</small></p>";
    print "<script type='text/javascript'>\n" .
          "function zfsguruFilterCfg(){var q=(document.getElementById('cfg_search').value||'').toLowerCase();var rows=document.querySelectorAll('.zfsguru-cfg-row');for(var i=0;i<rows.length;i++){var k=(rows[i].getAttribute('data-key')||'').toLowerCase();rows[i].style.display=(!q||k.indexOf(q)>=0)?'':'none';}}\n" .
          "document.addEventListener('DOMContentLoaded',function(){var e=document.getElementById('cfg_search');if(e){e.addEventListener('input',zfsguruFilterCfg);}});\n" .
          "</script>";

    print &ui_form_start("system.cgi", "post");
    print &ui_hidden("action", "preferences");
    print &ui_hidden("prefs_tab", "config");
    print &ui_hidden("save_prefs_group", "config");
    print &ui_table_start(L("TABLE_SYS_PREFS_CONFIG_KEYS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($cfg_file));

    my $idx = 0;
    for my $g (@$groups) {
        next unless ref($g) eq 'HASH';
        my $gname = $g->{name} || 'Other';
        my $keys = $g->{keys} || [];
        next unless @$keys;
        print &ui_table_span("<b>" . &html_escape($gname) . "</b>");
        for my $k (@$keys) {
            next unless defined $k && $k =~ /^[A-Za-z0-9_]+$/;
            next if $managed_pref_keys{$k};
            my $v = exists $kv->{$k} ? $kv->{$k} : '';
            print &ui_hidden("cfg_name_$idx", $k);
            print "<tr class='zfsguru-cfg-row' data-key='" . &html_escape($k) . "'>";
            print "<td><b>" . &html_escape($k) . "</b></td>";
            print "<td>" . &ui_textbox("cfg_val_$idx", $v, 80) . "</td>";
            print "</tr>";
            $idx++;
        }
    }
    print &ui_hidden("cfg_count", $idx);

    print &ui_table_row(
        L("ROW_ADD_NEW_KEYS"),
        &ui_textarea("cfg_new_entries", "", 6, 100) .
        "<br><small>" . L("HINT_CONFIG_KEY_FORMAT") . "</small>"
    );
    print &ui_table_end();
    print &ui_form_end([ [ "save_prefs_group", L("BTN_SAVE_SYSTEM_PREFS") ] ]);
}

sub prefcfg_managed_pref_keys {
    return qw(
      advanced_mode
      booting_expert_mode
      enable_smart_monitoring
      enable_benchmarking
      enable_system_update_ui
      monitor_pool_capacity_threshold
      monitor_alert_high_capacity
      monitor_disk_temperature_warning
      monitor_disk_temperature_critical
      log_level
      auto_refresh
      auto_refresh_interval
      animation_effects
      require_confirmation_for_pool_create
      require_confirmation_for_disk_format
      require_confirmation_for_pool_export
      ata_secure_erase_mode
      ata_secure_erase_pass
    );
}

sub action_cli {
    print &ui_subheading(L("SUB_SYS_CLI"));
    print "<p>" . L("MSG_SYS_CLI_WARNING") . "</p>";

    if ($in{'run_cli'}) {
        my $cmd = $in{'cli_command'} || '';
        if (!length $cmd) {
            print &ui_print_error(L("ERR_CLI_EMPTY_COMMAND"));
        } else {
            my ($rc, $out, $err) = run_cmd('/bin/sh', '-c', $cmd);
            print &ui_table_start(L("TABLE_CLI_RESULT"), "width=100%", 2);
            print &ui_table_row(L("ROW_COMMAND"), &html_escape($cmd));
            print &ui_table_row(L("ROW_RETURN_CODE"), $rc);
            print &ui_table_row(L("ROW_STDOUT"), "<pre>" . &html_escape($out || '') . "</pre>");
            print &ui_table_row(L("ROW_STDERR"), "<pre>" . &html_escape($err || '') . "</pre>");
            print &ui_table_end();
        }
    }

    print &ui_form_start("system.cgi", "post");
    print &ui_hidden("action", "cli");
    print &ui_hidden("run_cli", 1);
    print &ui_table_start(L("TABLE_CLI_INPUT"), "width=100%", 2);
    print &ui_table_row(L("ROW_COMMAND"), &ui_textbox("cli_command", "", 80));
    print &ui_table_end();
    print &ui_submit(L("BTN_RUN_COMMAND"), "run_cli", 0,
        "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
    print &ui_form_end();
}

sub action_tuning {
    my $loader_path = '/boot/loader.conf';
    my $tab = $in{'tuning_tab'} || 'auto';

    print &ui_subheading(L("SUB_SYS_TUNING"));
    print "<p>" . L("MSG_SYS_TUNING_INTRO", $loader_path) . "</p>";

    if (!-e $loader_path) {
        print &ui_print_error(L("ERR_SYS_TUNING_LOADERCONF_MISSING", $loader_path));
        return;
    }

    my $raw = read_file_text($loader_path);
    my $settings = loaderconf_parse($raw);

    my $physmem = sysctl_value('hw.physmem');
    my $active_profile = loaderconf_detect_profile($settings, $physmem);

    my @subtabs = (
        [ 'auto',     'TAB_SYS_TUNING_AUTO' ],
        [ 'zfs',      'TAB_SYS_TUNING_ZFS' ],
        [ 'advanced', 'TAB_SYS_TUNING_ADVANCED' ],
    );
    print zfsguru_print_tabs(
        script => 'system.cgi?action=tuning',
        active => $tab,
        tabs   => \@subtabs,
        param  => 'tuning_tab',
    );

    if ($tab eq 'auto') {
        if ($in{'apply_profile'}) {
            my $profile = $in{'mem_profile'} || '';
            my $profiles = loaderconf_profiles();
            if (!$profiles->{$profile}) {
                print &ui_print_error(L("ERR_SYS_TUNING_INVALID_PROFILE", $profile));
            } elsif (!$physmem || $physmem !~ /^\d+$/) {
                print &ui_print_error(L("ERR_SYS_TUNING_NO_PHYSMEM"));
            } else {
                my $new = loaderconf_profile_settings($profile, $physmem);
                if (!$in{'do_confirm_profile'}) {
                    print &ui_subheading(L("SUB_SYS_TUNING_PROFILE_PREVIEW", $profile));
                    my @heads = (L("COL_TUNING_VAR"), L("COL_TUNING_ENABLED"), L("COL_TUNING_VALUE"));
                    my @rows;
                    for my $k (sort keys %$new) {
                        my $d = $new->{$k} || {};
                        push @rows, [
                            "<tt>" . &html_escape($k) . "</tt>",
                            ($d->{enabled} ? L("VALUE_ENABLED") : L("VALUE_DISABLED")),
                            &html_escape(defined $d->{value} ? $d->{value} : ''),
                        ];
                    }
                    print &ui_columns_table(\@heads, 100, \@rows, undef, 1,
                        L("TABLE_SYS_TUNING_PROFILE_PREVIEW"), L("VALUE_NONE"));

                    print &ui_form_start("system.cgi", "post");
                    print &ui_hidden("action", "tuning");
                    print &ui_hidden("tuning_tab", "auto");
                    print &ui_hidden("apply_profile", 1);
                    print &ui_hidden("do_confirm_profile", 1);
                    print &ui_hidden("mem_profile", $profile);
                    print &ui_table_start(L("TABLE_SYS_TUNING_PROFILE_CONFIRM"), "width=100%", 2);
                    print &ui_table_row(L("ROW_CONFIRM"),
                        &ui_checkbox("confirm_profile", 1, L("LBL_CONFIRM_TUNING_PROFILE"), 0));
                    print &ui_table_end();
                    print &ui_submit(L("BTN_APPLY_PROFILE"), "do_confirm_profile", 0,
                        "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
                    print &ui_form_end();
                    return;
                }

                if (!$in{'confirm_profile'}) {
                    print &ui_print_error(L("ERR_CONFIRM_TUNING_PROFILE_REQUIRED"));
                } else {
                    eval {
                        my $backup = loaderconf_update_file($loader_path, $new);
                        log_info("Applied loader.conf tuning profile=$profile backup=$backup");
                        my $msg = L("SUCCESS_SYS_TUNING_PROFILE_APPLIED", $profile);
                        $msg .= " " . L("MSG_BACKUP_FILE", $backup) if $backup;
                        print &ui_print_success($msg);
                        print &ui_alert(L("WARN_REBOOT_REQUIRED"), 'warning');
                    };
                    if ($@) {
                        print &ui_print_error(L("ERR_SYS_TUNING_SAVE_FAILED", $@));
                    }
                }
            }
        }

        my $kmem = sysctl_value('vm.kmem_size');
        my $kmem_max = sysctl_value('vm.kmem_size_max');
        my $arc_min = sysctl_value('vfs.zfs.arc_min');
        my $arc_max = sysctl_value('vfs.zfs.arc_max');

        print &ui_table_start(L("TABLE_SYS_TUNING_STATUS"), "width=100%", 2);
        print &ui_table_row(L("ROW_PHYSMEM"), bytes_to_human($physmem));
        print &ui_table_row(L("ROW_KMEM_SIZE"), bytes_to_human($kmem));
        print &ui_table_row(L("ROW_KMEM_SIZE_MAX"), bytes_to_human($kmem_max));
        print &ui_table_row(L("ROW_ARC_MIN"), bytes_to_human($arc_min));
        print &ui_table_row(L("ROW_ARC_MAX"), bytes_to_human($arc_max));
        print &ui_table_row(L("ROW_TUNING_PROFILE_ACTIVE"), &html_escape($active_profile || L("VALUE_UNKNOWN")));
        print &ui_table_end();

        my $profiles = loaderconf_profiles();
        my @pref_order = qw(none minimal conservative balanced performance aggressive);
        my @opts;
        for my $name (@pref_order) {
            next unless exists $profiles->{$name};
            my $label = L("OPT_TUNING_PROFILE_" . uc($name));
            push @opts, [ $name, $label ];
        }

        print &ui_alert(L("MSG_SYS_TUNING_PROFILE_MODERN_NOTE"), 'info');
        print "<div style='margin:6px 0 12px 0'>";
        print "<b>" . L("LBL_PROFILE_GUIDE") . "</b>";
        print "<ul style='margin:6px 0 0 18px'>";
        print "<li><b>None</b>: " . L("HINT_TUNING_PROFILE_NONE") . "</li>";
        print "<li><b>Minimal</b>: " . L("HINT_TUNING_PROFILE_MINIMAL") . "</li>";
        print "<li><b>Conservative</b>: " . L("HINT_TUNING_PROFILE_CONSERVATIVE") . "</li>";
        print "<li><b>Balanced</b>: " . L("HINT_TUNING_PROFILE_BALANCED") . "</li>";
        print "<li><b>Performance</b>: " . L("HINT_TUNING_PROFILE_PERFORMANCE") . "</li>";
        print "<li><b>Aggressive</b>: " . L("HINT_TUNING_PROFILE_AGGRESSIVE") . "</li>";
        print "</ul>";
        print "</div>";

        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "tuning");
        print &ui_hidden("tuning_tab", "auto");
        print &ui_hidden("apply_profile", 1);
        print &ui_table_start(L("TABLE_SYS_TUNING_PROFILE"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_TUNING_PROFILE_SELECT"),
            &ui_select("mem_profile", ($active_profile || 'none'), \@opts)
        );
        print &ui_table_end();
        print &ui_submit(L("BTN_APPLY_PROFILE"), "apply_profile", 0,
            "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
        print &ui_form_end();
        return;
    }

    if ($tab eq 'zfs') {
        my @vars = loaderconf_zfs_tuning_vars();

        if ($in{'save_zfs_tuning'}) {
            my $count = int($in{'zfs_count'} || 0);
            my %new;
            my $need_confirm = 0;
            for my $i (0 .. $count - 1) {
                my $name = $in{"zfs_name_$i"} || '';
                next unless $name;
                next unless $name =~ /^[A-Za-z0-9._-]+$/;
                my $enabled = $in{"zfs_enabled_$i"} ? 1 : 0;
                my $val = defined $in{"zfs_value_$i"} ? $in{"zfs_value_$i"} : '';
                $val =~ s/[\r\n]//g;
                if ($enabled && !length $val) {
                    print &ui_print_error(L("ERR_SYS_TUNING_EMPTY_VALUE", $name));
                    return;
                }
                my $old = $settings->{$name} || { enabled => 0, value => '' };
                $new{$name} = {
                    enabled => $enabled,
                    value   => (length($val) ? $val : ($old->{value} || '')),
                };
                if ($enabled && ($name eq 'vfs.zfs.cache_flush_disable' || $name eq 'vfs.zfs.zil_disable')) {
                    $need_confirm = 1;
                }
            }

            if ($need_confirm && !$in{'confirm_dangerous_tuning'}) {
                print &ui_alert(L("WARN_SYS_TUNING_DANGEROUS"), 'warning');
                print &ui_print_error(L("ERR_SYS_TUNING_CONFIRM_DANGEROUS_REQUIRED"));
                # fallthrough and re-render form with current values
            } else {
                eval {
                    my $backup = loaderconf_update_file($loader_path, \%new);
                    log_info("Updated loader.conf ZFS tuning backup=$backup");
                    my $msg = L("SUCCESS_SYS_TUNING_SAVED");
                    $msg .= " " . L("MSG_BACKUP_FILE", $backup) if $backup;
                    print &ui_print_success($msg);
                    print &ui_alert(L("WARN_REBOOT_REQUIRED"), 'warning');
                    $raw = read_file_text($loader_path);
                    $settings = loaderconf_parse($raw);
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SYS_TUNING_SAVE_FAILED", $@));
                }
            }
        }

        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "tuning");
        print &ui_hidden("tuning_tab", "zfs");
        print &ui_hidden("save_zfs_tuning", 1);
        print &ui_hidden("zfs_count", scalar(@vars));

        print &ui_alert(L("MSG_SYS_TUNING_ZFS_VALUE_NOTE"), 'info');

        my @heads = (
            L("COL_TUNING_VAR"),
            L("COL_TUNING_ENABLED"),
            L("COL_TUNING_VALUE_CURRENT"),
            L("COL_TUNING_VALUE_RECOMMENDED"),
            L("COL_TUNING_DESC"),
        );

        my @data;
        for my $i (0 .. $#vars) {
            my $var = $vars[$i]{name};
            my $desc = $vars[$i]{desc};
            my $cur = $settings->{$var} || { enabled => 0, value => '' };
            my $enabled = $cur->{enabled} ? 1 : 0;
            my $val = defined $cur->{value} ? $cur->{value} : '';
            my $recommended = defined($vars[$i]{recommended}) ? $vars[$i]{recommended} : L("VALUE_NONE");
            push @data, [
                "<tt>" . &html_escape($var) . "</tt>" . &ui_hidden("zfs_name_$i", $var),
                &ui_checkbox("zfs_enabled_$i", 1, "", $enabled),
                &ui_textbox("zfs_value_$i", $val, 20),
                &html_escape($recommended),
                $desc,
            ];
        }

        print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_SYS_TUNING_ZFS"), L("VALUE_NONE"));
        print &ui_alert(L("WARN_SYS_TUNING_DANGEROUS"), 'warning');
        print &ui_checkbox("confirm_dangerous_tuning", 1, L("LBL_CONFIRM_DANGEROUS_TUNING"), 0);
        print "<br><br>";
        print &ui_submit(L("BTN_SAVE_TUNING"), "save_zfs_tuning", 0,
            "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
        print &ui_form_end();
        return;
    }

    # tab = advanced
    if ($in{'save_advanced_tuning'}) {
        my $count = int($in{'adv_count'} || 0);
        my %new;
        for my $i (0 .. $count - 1) {
            my $name = $in{"adv_name_$i"} || '';
            next unless $name;
            next unless $name =~ /^[A-Za-z0-9._-]+$/;
            my $enabled = $in{"adv_enabled_$i"} ? 1 : 0;
            my $val = defined $in{"adv_value_$i"} ? $in{"adv_value_$i"} : '';
            $val =~ s/[\r\n]//g;
            if ($enabled && !length $val) {
                print &ui_print_error(L("ERR_SYS_TUNING_EMPTY_VALUE", $name));
                return;
            }
            my $old = $settings->{$name} || { enabled => 0, value => '' };
            $new{$name} = {
                enabled => $enabled,
                value   => (length($val) ? $val : ($old->{value} || '')),
            };
        }

        my $new_name = $in{'new_tuning_name'} || '';
        my $new_value = defined $in{'new_tuning_value'} ? $in{'new_tuning_value'} : '';
        $new_value =~ s/[\r\n]//g;
        if (length $new_name) {
            if ($new_name !~ /^[A-Za-z0-9._-]+$/) {
                print &ui_print_error(L("ERR_SYS_TUNING_INVALID_VAR", $new_name));
                return;
            }
            if (!length $new_value) {
                print &ui_print_error(L("ERR_SYS_TUNING_EMPTY_VALUE", $new_name));
                return;
            }
            $new{$new_name} = { enabled => 1, value => $new_value };
        }

        eval {
            my $backup = loaderconf_update_file($loader_path, \%new);
            log_info("Updated loader.conf advanced tuning backup=$backup");
            my $msg = L("SUCCESS_SYS_TUNING_SAVED");
            $msg .= " " . L("MSG_BACKUP_FILE", $backup) if $backup;
            print &ui_print_success($msg);
            print &ui_alert(L("WARN_REBOOT_REQUIRED"), 'warning');
            $raw = read_file_text($loader_path);
            $settings = loaderconf_parse($raw);
        };
        if ($@) {
            print &ui_print_error(L("ERR_SYS_TUNING_SAVE_FAILED", $@));
        }
    }

    my @names = sort keys %$settings;
    print &ui_form_start("system.cgi", "post");
    print &ui_hidden("action", "tuning");
    print &ui_hidden("tuning_tab", "advanced");
    print &ui_hidden("save_advanced_tuning", 1);
    print &ui_hidden("adv_count", scalar(@names));

    my @heads = (L("COL_TUNING_VAR"), L("COL_TUNING_ENABLED"), L("COL_TUNING_VALUE"), L("COL_TUNING_DESC"));
    my @data;
    for my $i (0 .. $#names) {
        my $var = $names[$i];
        my $cur = $settings->{$var} || { enabled => 0, value => '' };
        my $enabled = $cur->{enabled} ? 1 : 0;
        my $val = defined $cur->{value} ? $cur->{value} : '';
        my $desc = loaderconf_var_description($var);
        push @data, [
            "<tt>" . &html_escape($var) . "</tt>" . &ui_hidden("adv_name_$i", $var),
            &ui_checkbox("adv_enabled_$i", 1, "", $enabled),
            &ui_textbox("adv_value_$i", $val, 24),
            $desc,
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_SYS_TUNING_ADVANCED"), L("VALUE_NONE"));

    print &ui_hr();
    print &ui_subheading(L("SUB_SYS_TUNING_ADD_VAR"));
    print &ui_table_start(L("TABLE_SYS_TUNING_ADD_VAR"), "width=100%", 2);
    print &ui_table_row(L("ROW_NEW_TUNING_NAME"), &ui_textbox("new_tuning_name", "", 40));
    print &ui_table_row(L("ROW_NEW_TUNING_VALUE"), &ui_textbox("new_tuning_value", "", 60));
    print &ui_table_end();
    print &ui_submit(L("BTN_SAVE_TUNING"), "save_advanced_tuning", 0,
        "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
    print &ui_form_end();
}

sub action_booting {
    my $expert = defined($in{'expert'})
        ? ($in{'expert'} ? 1 : 0)
        : ($config{'booting_expert_mode'} ? 1 : 0);
    my $do = $in{'do'} || '';

    if ($do) {
        my $back = "system.cgi?action=booting" . ($expert ? "&expert=1" : "");
        if (defined $in{'gen_pool'} && is_pool_name($in{'gen_pool'})) {
            $back .= "&gen_pool=" . &url_encode($in{'gen_pool'});
        }

        if ($do eq 'activate') {
            my $bootfs = $in{'bootfs'} || '';
            if (!is_dataset_name($bootfs)) {
                print &ui_print_error(L("ERR_INVALID_DATASET", $bootfs));
                return;
            }
            my $ds_type = zfs_dataset_type($bootfs);
            if (!defined($ds_type) || $ds_type eq '') {
                my $prop_type = zfs_get_prop_value($bootfs, 'type');
                $ds_type = lc($prop_type || '');
            }
            if (!$ds_type || $ds_type ne 'filesystem') {
                print &ui_print_error(L("ERR_SYS_BOOTFS_NOT_FILESYSTEM", $bootfs, ($ds_type || L("VALUE_UNKNOWN"))));
                return;
            }
            my ($pool) = split(/\//, $bootfs, 2);
            if (!is_pool_name($pool)) {
                print &ui_print_error(L("ERR_INVALID_POOL", $pool));
                return;
            }

            my $cmd = "zpool set bootfs=\"$bootfs\" $pool";
            if (!$in{'do_confirm'}) {
                print &ui_subheading(L("SUB_SYS_BOOTING_CONFIRM"));
                print &ui_alert(L("WARN_SYS_BOOTING_BOOT_IMPACT"), 'warning');
                print "<div class='zfsguru-code-block'><b>" . L("LBL_COMMAND_TO_EXECUTE") . "</b><br>" . &html_escape($cmd) . "</div>";
                print &ui_form_start("system.cgi", "post");
                print &ui_hidden("action", "booting");
                print &ui_hidden("do", "activate");
                print &ui_hidden("bootfs", $bootfs);
                print &ui_hidden("expert", 1) if $expert;
                print &ui_hidden("gen_pool", $in{'gen_pool'}) if defined $in{'gen_pool'} && is_pool_name($in{'gen_pool'});
                print &ui_checkbox("confirm_booting", 1, L("LBL_CONFIRM_BOOTING_ACTION"), 0);
                print "<br><br>";
                print &ui_submit(L("BTN_PROCEED"), "do_confirm", 0,
                    "style='background:#d9534f;color:#fff;border-color:#d43f3a;'") . " ";
                print &ui_link($back, L("BTN_CANCEL"));
                print &ui_form_end();
                return;
            }

            if (!$in{'confirm_booting'}) {
                print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
                print &ui_link($back, L("BTN_BACK"));
                return;
            }

            eval {
                zpool_set_bootfs($pool, $bootfs);
                log_info("Set bootfs for $pool to $bootfs");
                print &ui_print_success(L("SUCCESS_BOOTFS_SET", $pool));
            };
            if ($@) {
                print &ui_print_error(L("ERR_BOOTFS_SET_FAILED", $@));
            }
            return;
        } elsif ($do eq 'inactivate') {
            my $pool = $in{'pool'} || '';
            if (!is_pool_name($pool)) {
                print &ui_print_error(L("ERR_INVALID_POOL", $pool));
                return;
            }

            my $cmd = "zpool set bootfs=\"\" $pool";
            if (!$in{'do_confirm'}) {
                print &ui_subheading(L("SUB_SYS_BOOTING_CONFIRM"));
                print &ui_alert(L("WARN_SYS_BOOTING_BOOT_IMPACT"), 'warning');
                print &ui_alert(L("WARN_SYS_BOOTING_INACTIVATE"), 'warning');
                if (!$expert) {
                    print &ui_print_error(L("ERR_SYS_BOOTING_EXPERT_REQUIRED"));
                    print &ui_link($back, L("BTN_BACK"));
                    return;
                }
                print "<div class='zfsguru-code-block'><b>" . L("LBL_COMMAND_TO_EXECUTE") . "</b><br>" . &html_escape($cmd) . "</div>";
                print &ui_form_start("system.cgi", "post");
                print &ui_hidden("action", "booting");
                print &ui_hidden("do", "inactivate");
                print &ui_hidden("pool", $pool);
                print &ui_hidden("expert", 1);
                print &ui_hidden("gen_pool", $in{'gen_pool'}) if defined $in{'gen_pool'} && is_pool_name($in{'gen_pool'});
                print &ui_checkbox("confirm_booting", 1, L("LBL_CONFIRM_BOOTING_ACTION"), 0);
                print "<br><br>";
                print &ui_submit(L("BTN_PROCEED"), "do_confirm", 0,
                    "style='background:#d9534f;color:#fff;border-color:#d43f3a;'") . " ";
                print &ui_link($back, L("BTN_CANCEL"));
                print &ui_form_end();
                return;
            }

            if (!$expert) {
                print &ui_print_error(L("ERR_SYS_BOOTING_EXPERT_REQUIRED"));
                return;
            }

            if (!$in{'confirm_booting'}) {
                print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
                print &ui_link($back, L("BTN_BACK"));
                return;
            }

            eval {
                zpool_set_bootfs($pool, '');
                log_info("Cleared bootfs for $pool");
                print &ui_print_success(L("SUCCESS_BOOTFS_CLEARED", $pool));
            };
            if ($@) {
                print &ui_print_error(L("ERR_BOOTFS_SET_FAILED", $@));
            }
            return;
        } elsif ($do eq 'delete') {
            my $bootfs = $in{'bootfs'} || '';
            if (!is_dataset_name($bootfs)) {
                print &ui_print_error(L("ERR_INVALID_DATASET", $bootfs));
                return;
            }
            my ($pool) = split(/\//, $bootfs, 2);
            if (!is_pool_name($pool)) {
                print &ui_print_error(L("ERR_INVALID_POOL", $pool));
                return;
            }
            my $props = zpool_properties($pool, 'bootfs');
            my $active_bootfs = '';
            if (ref($props) eq 'HASH') {
                if (ref($props->{bootfs}) eq 'HASH') {
                    $active_bootfs = $props->{bootfs}{value} || '';
                } else {
                    $active_bootfs = $props->{bootfs} || '';
                }
            }
            my $is_active_bootfs = ($active_bootfs eq $bootfs) ? 1 : 0;
            if ($is_active_bootfs && !$expert) {
                print &ui_print_error(L("ERR_SYS_BOOTING_EXPERT_REQUIRED"));
                return;
            }

            my $cmd = "zfs destroy -R $bootfs";
            if (!$in{'do_confirm'}) {
                print &ui_subheading(L("SUB_SYS_BOOTING_CONFIRM"));
                print &ui_alert(L("WARN_SYS_BOOTING_DELETE"), 'warning');
                print &ui_alert(L("WARN_SYS_BOOTING_DELETE_ACTIVE"), 'warning') if $is_active_bootfs;
                print "<div class='zfsguru-code-block'><b>" . L("LBL_COMMAND_TO_EXECUTE") . "</b><br>" . &html_escape($cmd) . "</div>";
                print &ui_form_start("system.cgi", "post");
                print &ui_hidden("action", "booting");
                print &ui_hidden("do", "delete");
                print &ui_hidden("bootfs", $bootfs);
                print &ui_hidden("expert", 1) if $expert;
                print &ui_hidden("gen_pool", $in{'gen_pool'}) if defined $in{'gen_pool'} && is_pool_name($in{'gen_pool'});
                print &ui_checkbox("confirm_booting", 1, L("LBL_CONFIRM_BOOTING_ACTION"), 0);
                if ($is_active_bootfs) {
                    print "<br>";
                    print &ui_checkbox("confirm_booting_active_delete", 1, L("LBL_CONFIRM_BOOTING_ACTIVE_DELETE"), 0);
                }
                print "<br><br>";
                print &ui_submit(L("BTN_PROCEED"), "do_confirm", 0,
                    "style='background:#d9534f;color:#fff;border-color:#d43f3a;'") . " ";
                print &ui_link($back, L("BTN_CANCEL"));
                print &ui_form_end();
                return;
            }

            if (!$in{'confirm_booting'}) {
                print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
                print &ui_link($back, L("BTN_BACK"));
                return;
            }
            if ($is_active_bootfs && !$in{'confirm_booting_active_delete'}) {
                print &ui_print_error(L("ERR_CONFIRM_BOOTING_ACTIVE_DELETE_REQUIRED"));
                print &ui_link($back, L("BTN_BACK"));
                return;
            }

            eval {
                zfs_destroy($bootfs, '-R');
                log_info("Destroyed bootfs dataset: $bootfs");
                print &ui_print_success(L("SUCCESS_SYS_BOOTING_DATASET_DELETED", $bootfs));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SYS_BOOTING_DATASET_DELETE_FAILED", $@));
            }
            return;
        }

        print &ui_print_error(L("ERR_UNKNOWN_ACTION"));
        print &ui_link($back, L("BTN_BACK"));
        return;
    }

    print &ui_subheading(L("SUB_SYS_BOOTING"));
    print "<p>" . L("MSG_SYS_BOOTING_INTRO") . "</p>";

    if ($expert) {
        print &ui_alert(L("MSG_SYS_BOOTING_EXPERT_ON"), 'warning');
    } else {
        print "<p>" . &ui_link("system.cgi?action=booting&expert=1", L("LINK_ENABLE_EXPERT_MODE")) . "</p>";
    }

    my $pools = zpool_list([qw(name health)]);
    if (!$pools || !@$pools) {
        print &ui_print_error(L("NO_POOLS"));
        return;
    }

    my $bootable_pools = 0;
    my $bootable_installs = 0;

    my @heads = (
        L("COL_POOL"),
        L("COL_BOOTFS"),
        L("COL_USED"),
        L("COL_STATUS"),
        L("COL_ACTIONS"),
    );

    my @data;

    for my $p (@$pools) {
        my $pool = $p->{name} || next;
        next unless is_pool_name($pool);

        my $props = zpool_properties($pool, 'bootfs');
        my $bootfs = '-';
        if (ref($props) eq 'HASH') {
            if (ref($props->{bootfs}) eq 'HASH') {
                $bootfs = $props->{bootfs}{value} || '-';
            } else {
                $bootfs = $props->{bootfs} || '-';
            }
        }
        $bootfs = '-' if $bootfs eq '';
        $bootable_pools++ if $bootfs ne '-';

        my $prefix = "$pool/zfsguru";
        my $fslist = zfs_list([qw(name used mountpoint)], '-r', $prefix);
        next unless $fslist && @$fslist;

        for my $fs (@$fslist) {
            my $name = $fs->{name} || '';
            my $mp = $fs->{mountpoint} || '';
            next unless $name =~ /^\Q$pool\E\/zfsguru\/[^\/]+$/;
            next unless $mp eq 'legacy';
            $bootable_installs++;

            my ($inst) = $name =~ /\/([^\/]+)$/;
            my $used = $fs->{used} || '-';

            my $status = ($bootfs eq $name) ? L("VALUE_ACTIVATED") : L("VALUE_INACTIVE");
            my $status_cls = ($bootfs eq $name) ? 'zfsguru-status-ok' : 'zfsguru-status-unknown';
            my $status_html = "<span class='$status_cls'>" . &html_escape($status) . "</span>";

            my @btns;
            if ($bootfs ne $name) {
                push @btns, &ui_link_icon(
                    "system.cgi?action=booting&do=activate&bootfs=" . &url_encode($name) . ($expert ? "&expert=1" : ""),
                    L("BTN_ACTIVATE"),
                    undef,
                    { class => 'default' },
                );
            } else {
                if ($expert) {
                    push @btns, &ui_link_icon(
                        "system.cgi?action=booting&do=inactivate&pool=" . &url_encode($pool) . "&expert=1",
                        L("BTN_INACTIVATE_CLEAR_BOOTFS"),
                        undef,
                        { class => 'warning' },
                    );
                } else {
                    push @btns, "<span class='zfsguru-muted'>" . L("MSG_EXPERT_REQUIRED_INACTIVATE") . "</span>";
                }
            }

            my $can_delete = ($bootfs ne $name) || $expert;
            if ($can_delete) {
                my $del_btn = &ui_link_icon(
                    "system.cgi?action=booting&do=delete&bootfs=" . &url_encode($name) . ($expert ? "&expert=1" : ""),
                    L("BTN_DELETE"),
                    undef,
                    { class => 'danger' },
                );
                my $del_tip = "<span class='zfsguru-muted' title='" . &html_escape(L("TIP_DELETE_DATASET_RECURSIVE_NOT_DISK")) . "' style='margin-left:6px'>(" .
                              &html_escape(L("LBL_DESTROY_RECURSIVE_SHORT")) . ")</span>";
                push @btns, $del_btn . $del_tip;
            }

            my $actions = "<div class='zfsguru-actionlinks'>" . join(" ", @btns) . "</div>";

            push @data, [
                &html_escape($pool),
                &html_escape($inst || $name),
                &html_escape($used),
                $status_html,
                $actions,
            ];
        }
    }

    if ($bootable_installs < 1) {
        print &ui_print_error(L("MSG_SYS_BOOTING_NO_INSTALLS"));
        print "<p>" . &ui_link("advanced_pools.cgi", L("LINK_POOLS")) . " | " . &ui_link("uefi.cgi", L("LINK_UEFI")) . "</p>";
        return;
    }

    if ($bootable_pools > 1) {
        print &ui_alert(L("WARN_SYS_BOOTING_CONFLICT"), 'warning');
    } elsif ($bootable_installs == 1) {
        print &ui_alert(L("MSG_SYS_BOOTING_ONEBOOT"), 'info');
    } elsif ($bootable_installs > 1) {
        print &ui_alert(L("MSG_SYS_BOOTING_MULTIBOOT"), 'info');
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_SYS_BOOTING_LIST"), L("VALUE_NONE"));

    # General bootfs manager (any dataset, not only */zfsguru/* installs)
    print &ui_hr();
    print &ui_subheading(L("SUB_SYS_BOOTFS_GENERAL"));
    print "<p>" . L("MSG_SYS_BOOTFS_GENERAL") . "</p>";

    my $gen_pool = $in{'gen_pool'} || ($pools->[0]{name} || '');
    $gen_pool = ($pools->[0]{name} || '') unless is_pool_name($gen_pool);

    my $gen_props = $gen_pool ? zpool_properties($gen_pool, 'bootfs') : undef;
    my $gen_cur = '-';
    if (ref($gen_props) eq 'HASH') {
        if (ref($gen_props->{bootfs}) eq 'HASH') {
            $gen_cur = defined($gen_props->{bootfs}{value}) ? $gen_props->{bootfs}{value} : '-';
        } else {
            $gen_cur = defined($gen_props->{bootfs}) ? $gen_props->{bootfs} : '-';
        }
    }
    $gen_cur = '-' if !defined $gen_cur || $gen_cur eq '';

    print &ui_form_start("system.cgi", "get");
    print &ui_hidden("action", "booting");
    print &ui_hidden("expert", 1) if $expert;
    print &ui_table_start(L("TABLE_SYS_BOOTFS_GENERAL"), "width=100%", 2);
    print &ui_table_row(
        L("COL_POOL"),
        &ui_select("gen_pool", $gen_pool, [ map { [ $_->{name}, $_->{name} ] } @$pools ])
    );
    print &ui_table_row(L("ROW_BOOTFS_CURRENT"), &html_escape($gen_cur));
    print &ui_table_end();
    print &ui_form_end([ [ "refresh", L("BTN_REFRESH") ] ]);

    if ($gen_pool) {
        my $ds = zfs_list([qw(name type)], '-r', $gen_pool);
        my @opts = map {
            [ $_->{name}, $_->{name} ]
        } grep {
            defined($_->{name}) &&
            $_->{name} ne $gen_pool &&
            (defined($_->{type}) ? lc($_->{type}) : '') eq 'filesystem'
        } @{ $ds || [] };
        if (!@opts) {
            print &ui_print_error(L("ERR_SYS_BOOTFS_NO_DATASETS", $gen_pool));
        } else {
            my $sel = $gen_cur ne '-' ? $gen_cur : $opts[0][0];
            $sel = $opts[0][0] unless defined $sel && length $sel;

            print &ui_form_start("system.cgi", "post");
            print &ui_hidden("action", "booting");
            print &ui_hidden("do", "activate");
            print &ui_hidden("gen_pool", $gen_pool);
            print &ui_hidden("expert", 1) if $expert;
            print &ui_table_start(L("TABLE_SYS_BOOTFS_SET"), "width=100%", 2);
            print &ui_table_row(L("ROW_BOOTFS_DATASET"), &ui_select("bootfs", $sel, \@opts));
            print &ui_table_end();
            print &ui_submit(L("BTN_SET_BOOTFS"), "set_bootfs", 0,
                "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
            print &ui_form_end();

            if ($expert) {
                print &ui_form_start("system.cgi", "post");
                print &ui_hidden("action", "booting");
                print &ui_hidden("do", "inactivate");
                print &ui_hidden("pool", $gen_pool);
                print &ui_hidden("gen_pool", $gen_pool);
                print &ui_hidden("expert", 1);
                print &ui_submit(L("BTN_CLEAR_BOOTFS"), "clear_bootfs", 0,
                    "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
                print &ui_form_end();
            } else {
                my $link = "system.cgi?action=booting&expert=1&gen_pool=" . &url_encode($gen_pool);
                print &ui_alert(L("MSG_SYS_BOOTFS_CLEAR_EXPERT", $link), 'info');
            }
        }
    }

    print "<p>" . &ui_link("uefi.cgi", L("LINK_UEFI")) . " | " . &ui_link("disks.cgi", L("LINK_DISKS")) . "</p>";
    print "<p><small>" . L("MSG_SYS_BOOTING_SHORTCUTS_HELP") . "</small></p>";
}

sub action_update {
    my $tab = $in{'update_tab'} || 'overview';
    my $do  = $in{'update_do'}  || '';

    if ($do eq 'job_kill') {
        my $job = $in{'job'} || '';
        if ($job !~ /^update_[A-Za-z0-9_.-]+\.log$/) {
            print &ui_print_error(L("ERR_UPDATE_JOB_INVALID"));
        } else {
            my ($ok, $msg) = zfsguru_kill_job(file => $job);
            if ($ok) {
                print &ui_print_success(L("SUCCESS_UPDATE_JOB_KILLED", $job));
            } else {
                print &ui_print_error(L("ERR_UPDATE_JOB_KILL_FAILED", $msg || L("VALUE_UNKNOWN")));
            }
        }
        $tab = 'jobs';
    }

    if ($do eq 'clear_logs') {
        my ($ok, $err, $count) = zfsguru_clear_job_logs(prefix => 'update');
        if ($ok) {
            print &ui_print_success(L("SUCCESS_BG_LOGS_CLEARED", $count || 0));
        } else {
            print &ui_print_error(L("ERR_BG_LOGS_CLEAR_FAILED", $err || L("VALUE_UNKNOWN")));
        }
        $tab = 'jobs';
    }

    if ($do eq 'job_log') {
        my $job = $in{'job'} || '';
        if ($job !~ /^update_[A-Za-z0-9_.-]+\.log$/) {
            print &ui_print_error(L("ERR_UPDATE_JOB_INVALID"));
            return;
        }
        my $txt = zfsguru_read_job_log(file => $job);
        if (!length $txt) {
            print &ui_print_error(L("ERR_UPDATE_JOB_NOT_FOUND"));
            return;
        }
        print &ui_subheading(L("SUB_SYS_UPDATE_JOB_LOG", $job));
        print "<pre>" . &html_escape($txt) . "</pre>";
        print "<p><a class='button' href='system.cgi?action=update&update_tab=jobs'>" . L("BTN_BACK") . "</a></p>";
        return;
    }

    my $version = 'unknown';
    if (open(my $fh, '<', './module.info')) {
        while (<$fh>) {
            if (/^version=(.+)$/) {
                $version = $1;
                last;
            }
        }
        close($fh);
    }

    my $pools = zpool_list();
    my $datasets = zfs_list();
    my $zfs_ver = zfs_version() || L("VALUE_UNKNOWN");

    print &ui_subheading(L("SUB_SYS_UPDATE"));

    my @subtabs = (
        [ 'overview', 'TAB_SYS_UPDATE_OVERVIEW' ],
        [ 'freebsd',  'TAB_SYS_UPDATE_FREEBSD' ],
        [ 'pkg',      'TAB_SYS_UPDATE_PKG' ],
        [ 'offline',  'TAB_SYS_UPDATE_OFFLINE' ],
        [ 'custom',   'TAB_SYS_UPDATE_CUSTOM' ],
        [ 'jobs',     'TAB_SYS_UPDATE_JOBS' ],
    );
    print zfsguru_print_tabs(
        script => 'system.cgi?action=update',
        active => $tab,
        tabs   => \@subtabs,
        param  => 'update_tab',
    );

    # Common version info
    my $uname = '';
    if (-x '/usr/bin/uname') {
        my ($rc, $out, $err) = run_cmd('/usr/bin/uname', '-r');
        if ($rc == 0) { chomp $out; $uname = $out; }
    }
    my $fbsd_k = '';
    my $fbsd_u = '';
    if (-x '/bin/freebsd-version') {
        my ($krc, $kout, $kerr) = run_cmd('/bin/freebsd-version', '-k');
        if ($krc == 0) { chomp $kout; $fbsd_k = $kout; }
        my ($urc, $uout, $uerr) = run_cmd('/bin/freebsd-version', '-u');
        if ($urc == 0) { chomp $uout; $fbsd_u = $uout; }
    }
    my $pkg_ver = '';
    if (command_exists($zfsguru_lib::PKG || '/usr/local/sbin/pkg')) {
        my ($prc, $pout, $perr) = run_cmd(($zfsguru_lib::PKG || '/usr/local/sbin/pkg'), '-v');
        if ($prc == 0) { chomp $pout; $pkg_ver = $pout; }
    }

    if ($tab eq 'overview') {
        print "<p>" . L("MSG_SYS_UPDATE_INTRO") . "</p>";
        print &ui_table_start(L("TABLE_SYS_UPDATE_INFO"), "width=100%", 2);
        print &ui_table_row(L("ROW_MODULE_VERSION"), $version);
        print &ui_table_row(L("ROW_FREEBSD_KERNEL"), &html_escape($fbsd_k || $uname || L("VALUE_UNKNOWN")));
        print &ui_table_row(L("ROW_FREEBSD_USERLAND"), &html_escape($fbsd_u || L("VALUE_UNKNOWN")));
        print &ui_table_row(L("ROW_PKG_VERSION"), &html_escape($pkg_ver || L("VALUE_UNKNOWN")));
        print &ui_table_row(L("ROW_ZFS_VERSION"), &html_escape($zfs_ver));
        print &ui_table_row(L("ROW_TOTAL_POOLS"), scalar(@$pools));
        print &ui_table_row(L("ROW_TOTAL_DATASETS"), scalar(@$datasets));
        print &ui_table_end();

    }
    elsif ($tab eq 'freebsd') {
        my $cmd = $zfsguru_lib::FREEBSD_UPDATE || '/usr/sbin/freebsd-update';
        if (!command_exists($cmd)) {
            print &ui_print_error(L("ERR_UPDATE_CMD_MISSING", $cmd));
        } else {
            if ($in{'run_freebsd_update'}) {
                my $act = $in{'freebsd_update_action'} || 'fetch';
                my @cmds;
                if ($act eq 'fetch') {
                    push @cmds, [ $cmd, 'fetch' ];
                } elsif ($act eq 'install') {
                    push @cmds, [ $cmd, 'install' ];
                } elsif ($act eq 'fetch_install') {
                    push @cmds, [ $cmd, 'fetch' ], [ $cmd, 'install' ];
                } else {
                    print &ui_print_error(L("ERR_UPDATE_ACTION_INVALID"));
                    $act = '';
                }

                if ($act) {
                    my $needs_confirm = ($act =~ /install/);
                    if ($needs_confirm && !$in{'confirm_update'}) {
                        print &ui_alert(L("WARN_SYS_UPDATE_BOOT_IMPACT"), 'warning');
                        print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
                    } else {
                        my $label = ($act eq 'fetch') ? L("OPT_UPDATE_FETCH")
                                  : ($act eq 'install') ? L("OPT_UPDATE_INSTALL")
                                  : L("OPT_UPDATE_FETCH_INSTALL");
                        my $title = L("JOB_TITLE_FREEBSD_UPDATE", $label);
                        my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                            prefix   => 'update',
                            title    => $title,
                            commands => \@cmds,
                            env      => { PAGER => 'cat' },
                        );
                        if (!$ok) {
                            print &ui_print_error(L("ERR_UPDATE_JOB_START_FAILED", $err));
                        } else {
                            print &ui_print_success(L("SUCCESS_UPDATE_JOB_STARTED", $job_id));
                            print "<p>" . update_job_actions_html($log_file) . "</p>";
                            print &ui_alert(L("WARN_SYS_UPDATE_REBOOT"), 'warning') if ($act =~ /install/);
                        }
                    }
                }
            }

            print "<p>" . L("MSG_SYS_UPDATE_FREEBSD_INTRO", $cmd) . "</p>";
            print &ui_alert(L("WARN_SYS_UPDATE_REBOOT"), 'warning');

            print &ui_form_start("system.cgi", "post");
            print &ui_hidden("action", "update");
            print &ui_hidden("update_tab", "freebsd");
            print &ui_hidden("run_freebsd_update", 1);

            print &ui_table_start(L("TABLE_SYS_UPDATE_FREEBSD"), "width=100%", 2);
            print &ui_table_row(
                L("ROW_UPDATE_ACTION"),
                &ui_select("freebsd_update_action", ($in{'freebsd_update_action'} || 'fetch'), [
                    [ 'fetch',         L("OPT_UPDATE_FETCH") ],
                    [ 'install',       L("OPT_UPDATE_INSTALL") ],
                    [ 'fetch_install', L("OPT_UPDATE_FETCH_INSTALL") ],
                ])
            );
            print &ui_table_row(
                L("ROW_UPDATE_CONFIRM"),
                &ui_checkbox("confirm_update", 1, L("LBL_CONFIRM_UPDATE"), (defined $in{'confirm_update'} ? $in{'confirm_update'} : 1))
            );
            print &ui_table_end();

            print &ui_form_end([ [ "run_freebsd_update", L("BTN_START_UPDATE_JOB") ] ]);
        }
    }
    elsif ($tab eq 'pkg') {
        my $cmd = $zfsguru_lib::PKG || '/usr/local/sbin/pkg';
        if (!command_exists($cmd)) {
            print &ui_print_error(L("ERR_UPDATE_CMD_MISSING", $cmd));
        } else {
            if ($in{'run_pkg_update'}) {
                my $act = $in{'pkg_update_action'} || 'update';
                my @cmds;
                if ($act eq 'update') {
                    push @cmds, [ $cmd, 'update', '-f' ];
                } elsif ($act eq 'upgrade') {
                    push @cmds, [ $cmd, 'upgrade', '-y' ];
                } elsif ($act eq 'update_upgrade') {
                    push @cmds, [ $cmd, 'update', '-f' ], [ $cmd, 'upgrade', '-y' ];
                } else {
                    print &ui_print_error(L("ERR_UPDATE_ACTION_INVALID"));
                    $act = '';
                }

                if ($act) {
                    my $needs_confirm = ($act =~ /upgrade/);
                    if ($needs_confirm && !$in{'confirm_update'}) {
                        print &ui_alert(L("WARN_SYS_UPDATE_PKG_IMPACT"), 'warning');
                        print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
                    } else {
                        my $label = ($act eq 'update') ? L("OPT_PKG_UPDATE")
                                  : ($act eq 'upgrade') ? L("OPT_PKG_UPGRADE")
                                  : L("OPT_PKG_UPDATE_UPGRADE");
                        my $title = L("JOB_TITLE_PKG_UPDATE", $label);
                        my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                            prefix   => 'update',
                            title    => $title,
                            commands => \@cmds,
                            env      => { ASSUME_ALWAYS_YES => 'yes', PAGER => 'cat' },
                        );
                        if (!$ok) {
                            print &ui_print_error(L("ERR_UPDATE_JOB_START_FAILED", $err));
                        } else {
                            print &ui_print_success(L("SUCCESS_UPDATE_JOB_STARTED", $job_id));
                            print "<p>" . update_job_actions_html($log_file) . "</p>";
                        }
                    }
                }
            }

            if ($in{'run_pkg_install'}) {
                my ($pkgs, $bad) = update_parse_pkg_list($in{'pkg_install_list'} // '');
                if ($bad && @$bad) {
                    print &ui_print_error(L("ERR_PKG_INSTALL_INVALID", join(' ', @$bad)));
                } elsif (!$pkgs || !@$pkgs) {
                    print &ui_print_error(L("ERR_PKG_INSTALL_EMPTY"));
                } elsif (!$in{'confirm_update'}) {
                    print &ui_alert(L("WARN_SYS_UPDATE_PKG_INSTALL_IMPACT"), 'warning');
                    print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
                } else {
                    my @cmds;
                    push @cmds, [ $cmd, 'update', '-f' ] if $in{'pkg_install_update_first'};
                    my $chunk_size = 40;
                    my @queue = @$pkgs;
                    while (@queue) {
                        my @chunk = splice(@queue, 0, $chunk_size);
                        push @cmds, [ $cmd, 'install', '-y', @chunk ];
                    }

                    my $short = join(' ', @$pkgs[0 .. ($#$pkgs < 4 ? $#$pkgs : 4)]);
                    $short .= " ..." if @$pkgs > 5;

                    my $title = L("JOB_TITLE_PKG_INSTALL", $short);
                    my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                        prefix   => 'update',
                        title    => $title,
                        commands => \@cmds,
                        env      => { ASSUME_ALWAYS_YES => 'yes', PAGER => 'cat' },
                    );
                    if (!$ok) {
                        print &ui_print_error(L("ERR_UPDATE_JOB_START_FAILED", $err));
                    } else {
                        print &ui_print_success(L("SUCCESS_UPDATE_JOB_STARTED", $job_id));
                        print "<p>" . update_job_actions_html($log_file) . "</p>";
                    }
                }
            }

            print "<p>" . L("MSG_SYS_UPDATE_PKG_INTRO", $cmd) . "</p>";

            print &ui_form_start("system.cgi", "post");
            print &ui_hidden("action", "update");
            print &ui_hidden("update_tab", "pkg");
            print &ui_hidden("run_pkg_update", 1);

            print &ui_table_start(L("TABLE_SYS_UPDATE_PKG"), "width=100%", 2);
            print &ui_table_row(
                L("ROW_UPDATE_ACTION"),
                &ui_select("pkg_update_action", ($in{'pkg_update_action'} || 'update'), [
                    [ 'update',         L("OPT_PKG_UPDATE") ],
                    [ 'upgrade',        L("OPT_PKG_UPGRADE") ],
                    [ 'update_upgrade', L("OPT_PKG_UPDATE_UPGRADE") ],
                ])
            );
            print &ui_table_row(
                L("ROW_UPDATE_CONFIRM"),
                &ui_checkbox("confirm_update", 1, L("LBL_CONFIRM_UPDATE"), (defined $in{'confirm_update'} ? $in{'confirm_update'} : 1))
            );
            print &ui_table_end();

            print &ui_form_end([ [ "run_pkg_update", L("BTN_START_UPDATE_JOB") ] ]);

            print &ui_hr();
            print &ui_subheading(L("SUB_SYS_UPDATE_PKG_INSTALL"));
            print "<p>" . L("MSG_SYS_UPDATE_PKG_INSTALL_INTRO", $cmd) . "</p>";
            print &ui_alert(L("WARN_SYS_UPDATE_PKG_INSTALL_IMPACT"), 'warning');

            print &ui_form_start("system.cgi", "post");
            print &ui_hidden("action", "update");
            print &ui_hidden("update_tab", "pkg");
            print &ui_hidden("run_pkg_install", 1);

            print &ui_table_start(L("TABLE_SYS_UPDATE_PKG_INSTALL"), "width=100%", 2);
            print &ui_table_row(
                L("ROW_PKG_INSTALL_LIST"),
                &ui_textarea("pkg_install_list", ($in{'pkg_install_list'} || ''), 4, 80)
            );
            print &ui_table_row(
                L("ROW_PKG_INSTALL_UPDATE_FIRST"),
                &ui_checkbox("pkg_install_update_first", 1, L("LBL_PKG_INSTALL_UPDATE_FIRST"), $in{'pkg_install_update_first'} ? 1 : 0)
            );
            print &ui_table_row(
                L("ROW_UPDATE_CONFIRM"),
                &ui_checkbox("confirm_update", 1, L("LBL_CONFIRM_UPDATE"), (defined $in{'confirm_update'} ? $in{'confirm_update'} : 1))
            );
            print &ui_table_end();

            print &ui_form_end([ [ "run_pkg_install", L("BTN_PKG_INSTALL") ] ]);
        }
    }
    elsif ($tab eq 'offline') {
        if ($in{'offline_url_install'}) {
            if (!$in{'confirm_update'}) {
                print &ui_alert(L("WARN_SYS_UPDATE_OFFLINE_IMPACT"), 'warning');
                print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
            } else {
                my $url = $in{'offline_url'} // '';
                $url =~ s/[\r\n]//g;
                if (!length $url) {
                    print &ui_print_error(L("ERR_UPDATE_URL_EMPTY"));
                } elsif ($url !~ m{^https?://}i) {
                    print &ui_print_error(L("ERR_UPDATE_URL_INVALID", $url));
                } else {
                    my $upload_dir = $config{'update_upload_dir'} || '/var/tmp/zfsguru-uploads';
                    eval { update_ensure_dir($upload_dir); };
                    if ($@) {
                        print &ui_print_error(L("ERR_UPDATE_UPLOAD_DIR", $@));
                    } else {
                        my $safe = update_sanitize_filename(update_url_filename($url) || 'download.pkg');
                        my $stamp = time . "_" . $$ . "_" . int(rand(1000));
                        my $saved = "$upload_dir/$stamp-$safe";
                        my $workdir = "$upload_dir/work_$stamp";
                        eval { update_ensure_dir($workdir); };

                        my $title = L("JOB_TITLE_OFFLINE_URL_INSTALL", $safe);
                        my $run = sub {
                            print "Offline install URL: $url\n";
                            print "Saved as: $saved\n";
                            print "Workdir: $workdir\n\n";

                            my $fetch = $zfsguru_lib::FETCH || '/usr/bin/fetch';
                            die "fetch command missing: $fetch" unless command_exists($fetch);
                            my $rc = system($fetch, '-o', $saved, $url);
                            die "fetch failed" if $rc != 0;

                            update_offline_install_from_file($saved, $workdir);
                        };

                        my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                            prefix => 'update',
                            title  => $title,
                            run    => $run,
                            env    => { ASSUME_ALWAYS_YES => 'yes', PAGER => 'cat' },
                        );
                        if (!$ok) {
                            print &ui_print_error(L("ERR_UPDATE_JOB_START_FAILED", $err));
                        } else {
                            print &ui_print_success(L("SUCCESS_UPDATE_JOB_STARTED", $job_id));
                            print "<p>" . update_job_actions_html($log_file) . "</p>";
                        }
                    }
                }
            }
        }
        elsif ($in{'offline_install'}) {
            if (!$in{'confirm_update'}) {
                print &ui_alert(L("WARN_SYS_UPDATE_OFFLINE_IMPACT"), 'warning');
                print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
            } else {
                my ($tmp, $orig) = update_get_upload('offline_file');
                if (!$tmp) {
                    print &ui_print_error(L("ERR_UPDATE_NO_UPLOAD"));
                } else {
                    my $upload_dir = $config{'update_upload_dir'} || '/var/tmp/zfsguru-uploads';
                    eval { update_ensure_dir($upload_dir); };
                    if ($@) {
                        print &ui_print_error(L("ERR_UPDATE_UPLOAD_DIR", $@));
                    } else {
                        my $safe = update_sanitize_filename($orig || 'upload.bin');
                        my $stamp = time . "_" . $$ . "_" . int(rand(1000));
                        my $saved = "$upload_dir/$stamp-$safe";
                        eval {
                            update_copy_file_bin($tmp, $saved);
                            unlink($tmp);
                        };
                        if ($@) {
                            print &ui_print_error(L("ERR_UPDATE_UPLOAD_SAVE_FAILED", $@));
                        } else {
                            my $title = L("JOB_TITLE_OFFLINE_INSTALL", $safe);
                            my $workdir = "$upload_dir/work_$stamp";
                            eval { update_ensure_dir($workdir); };
                            my $run = sub { update_offline_install_from_file($saved, $workdir); };

                            my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                                prefix => 'update',
                                title  => $title,
                                run    => $run,
                                env    => { ASSUME_ALWAYS_YES => 'yes', PAGER => 'cat' },
                            );
                            if (!$ok) {
                                print &ui_print_error(L("ERR_UPDATE_JOB_START_FAILED", $err));
                            } else {
                                print &ui_print_success(L("SUCCESS_UPDATE_JOB_STARTED", $job_id));
                                print "<p>" . update_job_actions_html($log_file) . "</p>";
                            }
                        }
                    }
                }
            }
        }

        print "<p>" . L("MSG_SYS_UPDATE_OFFLINE_INTRO") . "</p>";
        print &ui_alert(L("WARN_SYS_UPDATE_OFFLINE_IMPACT"), 'warning');

        print &ui_subheading(L("SUB_SYS_UPDATE_OFFLINE_UPLOAD"));
        print &ui_form_start("system.cgi", "form-data");
        print &ui_hidden("action", "update");
        print &ui_hidden("update_tab", "offline");
        print &ui_hidden("offline_install", 1);

        print &ui_table_start(L("TABLE_SYS_UPDATE_OFFLINE"), "width=100%", 2);
        print &ui_table_row(L("ROW_UPDATE_OFFLINE_FILE"), &ui_upload("offline_file", 60));
        print &ui_table_row(
            L("ROW_UPDATE_CONFIRM"),
            &ui_checkbox("confirm_update", 1, L("LBL_CONFIRM_UPDATE"), 0)
        );
        print &ui_table_end();

        print &ui_form_end([ [ "offline_install", L("BTN_START_UPDATE_JOB") ] ]);

        print &ui_hr();
        print &ui_subheading(L("SUB_SYS_UPDATE_OFFLINE_URL"));
        print "<p>" . L("MSG_SYS_UPDATE_OFFLINE_URL_INTRO") . "</p>";

        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "update");
        print &ui_hidden("update_tab", "offline");
        print &ui_hidden("offline_url_install", 1);

        print &ui_table_start(L("TABLE_SYS_UPDATE_OFFLINE_URL"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_UPDATE_OFFLINE_URL"),
            &ui_textbox("offline_url", ($in{'offline_url'} || ''), 80)
        );
        print &ui_table_row(
            L("ROW_UPDATE_CONFIRM"),
            &ui_checkbox("confirm_update", 1, L("LBL_CONFIRM_UPDATE"), 0)
        );
        print &ui_table_end();

        print &ui_form_end([ [ "offline_url_install", L("BTN_START_UPDATE_JOB") ] ]);
    }
    elsif ($tab eq 'custom') {
        if ($in{'run_custom_update'}) {
            my $cmd = $in{'custom_cmd'} // '';
            $cmd =~ s/\r//g;
            if (!length $cmd) {
                print &ui_print_error(L("ERR_CLI_EMPTY_COMMAND"));
            } elsif (!$in{'confirm_update'}) {
                print &ui_alert(L("WARN_SYS_UPDATE_CUSTOM_DANGEROUS"), 'warning');
                print &ui_print_error(L("ERR_CONFIRM_REQUIRED"));
            } else {
                my $title = L("JOB_TITLE_CUSTOM_UPDATE");
                my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                    prefix   => 'update',
                    title    => $title,
                    commands => [ [ '/bin/sh', '-c', $cmd ] ],
                    env      => { ASSUME_ALWAYS_YES => 'yes', PAGER => 'cat' },
                );
                if (!$ok) {
                    print &ui_print_error(L("ERR_UPDATE_JOB_START_FAILED", $err));
                } else {
                    print &ui_print_success(L("SUCCESS_UPDATE_JOB_STARTED", $job_id));
                    print "<p>" . update_job_actions_html($log_file) . "</p>";
                }
            }
        }

        print "<p>" . L("MSG_SYS_UPDATE_CUSTOM_INTRO") . "</p>";
        print &ui_alert(L("WARN_SYS_UPDATE_CUSTOM_DANGEROUS"), 'warning');

        print &ui_form_start("system.cgi", "post");
        print &ui_hidden("action", "update");
        print &ui_hidden("update_tab", "custom");
        print &ui_hidden("run_custom_update", 1);

        print &ui_table_start(L("TABLE_SYS_UPDATE_CUSTOM"), "width=100%", 2);
        print &ui_table_row(
            L("ROW_COMMAND"),
            &ui_textarea("custom_cmd", ($in{'custom_cmd'} || ''), 6, 80)
        );
        print &ui_table_row(
            L("ROW_UPDATE_CONFIRM"),
            &ui_checkbox("confirm_update", 1, L("LBL_CONFIRM_UPDATE"), 0)
        );
        print &ui_table_end();

        print &ui_form_end([ [ "run_custom_update", L("BTN_START_UPDATE_JOB") ] ]);
    }
    elsif ($tab eq 'jobs') {
        print "<p>" . L("MSG_SYS_UPDATE_JOBS") . "</p>";
        print "<p>";
        print &ui_link_icon("system.cgi?action=update&update_tab=jobs", L("BTN_REFRESH"), undef, { class => 'primary' });
        print " ";
        print &ui_form_start("system.cgi", "post", "style='display:inline'");
        print &ui_hidden("action", "update");
        print &ui_hidden("update_tab", "jobs");
        print &ui_hidden("update_do", "clear_logs");
        print &ui_submit(L("BTN_EMPTY_LOGS"), "clear_logs", 0,
            "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
        print &ui_form_end();
        print "</p>";

        my $jobs = zfsguru_list_jobs(prefix => 'update');
        my @heads = (L("COL_JOB"), L("COL_STATUS"), L("COL_UPDATED"), L("COL_ACTIONS"));
        my @data;
        for my $j (@{ $jobs || [] }) {
            my $f = $j->{file} || next;
            my $st = $j->{status} || '';
            my $st_text =
                $st eq 'ok'      ? L("VALUE_JOB_DONE") :
                $st eq 'failed'  ? L("VALUE_JOB_FAILED") :
                $st eq 'killed'  ? L("VALUE_JOB_KILLED") :
                $st eq 'running' ? L("VALUE_JOB_RUNNING") :
                $st eq 'stale'   ? L("VALUE_JOB_STALE") :
                                   L("VALUE_UNKNOWN");
            my $st_class =
                $st eq 'ok'      ? 'zfsguru-status-ok' :
                $st eq 'failed'  ? 'zfsguru-status-bad' :
                $st eq 'running' ? 'zfsguru-status-warn' :
                $st eq 'killed'  ? 'zfsguru-status-unknown' :
                $st eq 'stale'   ? 'zfsguru-status-bad' :
                                   'zfsguru-status-unknown';
            push @data, [
                &html_escape($f),
                "<span class='$st_class'>" . &html_escape($st_text) . "</span>",
                &html_escape($j->{mtime} || ''),
                update_job_actions_html($f, $st),
            ];
        }
        print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_SYS_UPDATE_JOBS"), L("VALUE_NONE"));
    }
    else {
        print &ui_print_error(L("ERR_UPDATE_ACTION_INVALID"));
    }
}

sub action_shutdown {
    if ($in{'reboot_now'} || $in{'poweroff_now'}) {
        if (!$in{'confirm_shutdown'}) {
            print &ui_print_error(L("ERR_CONFIRM_SHUTDOWN_REQUIRED"));
        } else {
            eval {
                if ($in{'reboot_now'}) {
                    system_reboot_now();
                } elsif ($in{'poweroff_now'}) {
                    system_poweroff_now();
                }
            };
            if ($@) {
                print &ui_print_error(L("ERR_SHUTDOWN_COMMAND_FAILED", $@));
            } else {
                my $msg = $in{'reboot_now'} ? L("SUCCESS_REBOOT_INITIATED") : L("SUCCESS_POWEROFF_INITIATED");
                print &ui_print_success($msg);
            }
        }
    }

    print &ui_subheading(L("SUB_SYS_SHUTDOWN"));
    print "<p>" . L("MSG_SHUTDOWN_WARNING") . "</p>";

    print &ui_form_start("system.cgi", "post");
    print &ui_hidden("action", "shutdown");
    print &ui_checkbox("confirm_shutdown", 1, L("LBL_CONFIRM_SHUTDOWN"), 0);
    print "<br><br>";
    print &ui_submit(L("BTN_REBOOT_NOW"), "reboot_now", 0,
        "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
    print " ";
    print &ui_submit(L("BTN_POWEROFF_NOW"), "poweroff_now", 0,
        "style='background:#d9534f;color:#fff;border-color:#d43f3a;'");
    print &ui_form_end();
}

sub update_job_actions_html {
    my ($log_file, $raw_st) = @_;
    return '' unless defined $log_file && $log_file =~ /^[A-Za-z0-9_.-]+\.log$/;
    my $view = "system.cgi?action=update&update_do=job_log&job=" . &url_encode($log_file);
    my $view_btn = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_VIEW_LOG"))
                 . "' onclick=\"window.location.href='" . &html_escape($view)
                 . "'\" style='background:#0275d8;color:#fff;border-color:#0275d8'>";
    my $kill_btn = '';
    if (!defined($raw_st) || $raw_st eq '' || $raw_st eq 'running') {
        $kill_btn = "<form method='post' action='system.cgi' style='display:inline;margin-left:6px'>"
                  . &ui_hidden("action", "update")
                  . &ui_hidden("update_tab", "jobs")
                  . &ui_hidden("update_do", "job_kill")
                  . &ui_hidden("job", $log_file)
                  . "<input type='submit' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                  . "' style='background:#d9534f;color:#fff;border-color:#d9534f'>"
                  . "</form>";
    } else {
        $kill_btn = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                  . "' disabled='disabled' title='" . &html_escape(L("MSG_JOB_NOT_RUNNING"))
                  . "' style='margin-left:6px;background:#d9534f;color:#fff;border-color:#d9534f;opacity:.45;cursor:not-allowed'>";
    }
    return $view_btn . $kill_btn;
}

sub migration_dir {
    return $config{'migration_dir'} || '/var/tmp/zfsguru-migration';
}

sub list_migration_archives {
    my $dir = migration_dir();
    return [] unless $dir && $dir =~ m{^/} && -d $dir;

    opendir my $dh, $dir or return [];
    my @files = readdir $dh;
    closedir $dh;

    my @out;
    for my $f (@files) {
        next unless $f =~ /^zfsguru_migration_\d{8}-\d{6}\.tgz$/;
        my $path = "$dir/$f";
        next unless -r $path;
        my @st = stat($path);
        my $size = $st[7] || 0;
        my $mtime = $st[9] || 0;
        push @out, {
            file => $f,
            size_bytes => $size,
            size => bytes_to_human($size),
            mtime_epoch => $mtime,
            mtime => $mtime ? scalar(localtime($mtime)) : '',
        };
    }

    @out = sort { $b->{mtime_epoch} <=> $a->{mtime_epoch} } @out;
    return \@out;
}

sub action_migration_download {
    my $file = $in{'file'} || '';
    if (!$file || $file !~ /^zfsguru_migration_\d{8}-\d{6}\.tgz$/) {
        print "Content-type: text/plain\n\nInvalid archive name.\n";
        return;
    }

    eval { require_root(); };
    if ($@) {
        print "Content-type: text/plain\n\nThis operation requires root.\n";
        return;
    }

    eval { acl_require_feature('system'); };
    if ($@) {
        print "Content-type: text/plain\n\nAccess denied.\n";
        return;
    }

    my $dir = migration_dir();
    my $path = "$dir/$file";
    if (!$dir || $dir !~ m{^/} || !-r $path) {
        print "Content-type: text/plain\n\nArchive not found.\n";
        return;
    }

    my $size = (stat($path))[7] || 0;
    print "Content-type: application/gzip\n";
    print "Content-Disposition: attachment; filename=\"$file\"\n";
    print "Content-Length: $size\n" if $size;
    print "\n";

    open my $fh, '<', $path or return;
    binmode($fh);
    binmode(STDOUT);
    my $buf;
    while (read($fh, $buf, 65536)) {
        print $buf;
    }
    close $fh;
}

sub path_dirname_simple {
    my ($p) = @_;
    $p = '' unless defined $p;
    $p =~ s{/+}{/}g;
    return '/' if $p eq '/' || $p eq '';
    $p =~ s{/$}{};
    $p =~ s{/[^/]*$}{};
    return $p eq '' ? '/' : $p;
}

sub migration_rel_from_abs {
    my ($abs) = @_;
    return '' unless defined $abs && length $abs;
    return '' unless $abs =~ m{^/};
    (my $rel = $abs) =~ s{^/}{};
    return $rel;
}

sub migration_is_safe_tar_entry {
    my ($e) = @_;
    return 0 unless defined $e && length $e;
    return 0 if $e =~ m{^/};
    return 0 if $e =~ m{(?:^|/)\.\.(?:/|$)};
    return 0 if $e =~ /\\/;
    return 1;
}

sub migration_tar_list_entries {
    my ($archive_path) = @_;
    die "Invalid archive path" unless defined $archive_path && $archive_path =~ m{^/};
    die "Archive not readable" unless -r $archive_path;

    my $tar = $zfsguru_lib::TAR || '/usr/bin/tar';
    my ($rc, $out, $err) = run_cmd($tar, '-tzf', $archive_path);
    die "tar list failed: $err" if $rc != 0;

    my @entries;
    for my $ln (split /\n/, ($out || '')) {
        $ln =~ s/\r$//;
        $ln =~ s{^\./}{};
        next unless length $ln;
        die "Unsafe tar entry: $ln" unless migration_is_safe_tar_entry($ln);
        push @entries, $ln;
    }

    die "Archive is empty" unless @entries;
    return \@entries;
}

sub migration_tar_read_file {
    my ($archive_path, $rel_path) = @_;
    die "Invalid archive path" unless defined $archive_path && $archive_path =~ m{^/};
    die "Invalid relative path" unless defined $rel_path && length $rel_path;
    die "Unsafe tar path" unless migration_is_safe_tar_entry($rel_path);

    my $tar = $zfsguru_lib::TAR || '/usr/bin/tar';
    my ($rc, $out, $err) = run_cmd($tar, '-xOzf', $archive_path, $rel_path);
    die "tar extract failed for $rel_path: $err" if $rc != 0;
    return defined $out ? $out : '';
}

sub migration_write_file_bin_preserve {
    my ($dst, $content) = @_;
    die "Invalid dest" unless defined $dst && $dst =~ m{^/};
    $content = '' unless defined $content;

    my ($mode, $uid, $gid);
    if (-e $dst) {
        my @st = stat($dst);
        $mode = $st[2] & 07777;
        $uid  = $st[4];
        $gid  = $st[5];
    }

    open my $fh, '>', $dst or die "open $dst: $!";
    binmode($fh);
    print $fh $content or die "write $dst: $!";
    close $fh or die "close $dst: $!";

    if (defined $mode) {
        chmod $mode, $dst;
        chown $uid, $gid, $dst;
    }

    return 1;
}

sub migration_restore_archive {
    my (%opt) = @_;
    my $archive_path = $opt{archive_path} || '';
    my $include = $opt{include};
    my $backup_dir = $opt{backup_dir} || '';

    die "Invalid archive path" unless $archive_path && $archive_path =~ m{^/} && -r $archive_path;
    die "Missing include list" unless ref($include) eq 'ARRAY' && @$include;

    if (!$backup_dir) {
        my $stamp = time . "_" . $$ . "_" . int(rand(1000));
        $backup_dir = migration_dir() . "/restore_backup_$stamp";
    }
    die "Backup dir must be absolute" unless $backup_dir =~ m{^/};

    update_ensure_dir($backup_dir);

    print "Restore archive: $archive_path\n";
    print "Include groups: " . join(', ', @$include) . "\n";
    print "Backup dir: $backup_dir\n\n";

    my $entries = migration_tar_list_entries($archive_path);
    my %in_archive = map { $_ => 1 } @$entries;

    my $targets = migration_targets_for_include($include);

    my ($restored, $skipped) = (0, 0);
    for my $dst (@$targets) {
        next unless defined $dst && $dst =~ m{^/};
        my $rel = migration_rel_from_abs($dst);
        if (!$rel || !$in_archive{$rel}) {
            print "SKIP (not in archive): $dst\n";
            $skipped++;
            next;
        }

        print "RESTORE: $dst\n";

        my $data = migration_tar_read_file($archive_path, $rel);

        my $dst_dir = path_dirname_simple($dst);
        update_ensure_dir($dst_dir);

        if (-e $dst) {
            my $bak = "$backup_dir/$rel";
            my $bak_dir = path_dirname_simple($bak);
            update_ensure_dir($bak_dir);
            update_copy_file_bin($dst, $bak);
            print "  backup: $bak\n";
        }

        migration_write_file_bin_preserve($dst, $data);
        $restored++;
    }

    print "\nRestored: $restored\n";
    print "Skipped : $skipped\n";
}

sub migration_targets_for_include {
    my ($include) = @_;
    die "Missing include list" unless ref($include) eq 'ARRAY';

    my @targets;
    if (grep { $_ eq 'module' } @$include) {
        push @targets, "$config_directory/config" if $config_directory && $config_directory =~ m{^/};
    }
    if (grep { $_ eq 'rc' } @$include) {
        push @targets, qw(/etc/rc.conf /boot/loader.conf /boot/loader.conf.local /etc/sysctl.conf /etc/fstab /etc/pf.conf);
    }
    if (grep { $_ eq 'sharing' } @$include) {
        push @targets, qw(/etc/exports /usr/local/etc/smb4.conf /etc/ctl.conf /etc/ssh/sshd_config);
    }
    if (grep { $_ eq 'network' } @$include) {
        push @targets, qw(/etc/hosts /etc/resolv.conf);
    }

    my %seen;
    @targets = grep { defined $_ && $_ =~ m{^/} && !$seen{$_}++ } @targets;
    return \@targets;
}

sub migration_build_restore_plan {
    my (%opt) = @_;
    my $archive_path = $opt{archive_path} || '';
    my $include = $opt{include};

    die "Invalid archive path" unless $archive_path && $archive_path =~ m{^/} && -r $archive_path;
    die "Missing include list" unless ref($include) eq 'ARRAY' && @$include;

    my $entries = migration_tar_list_entries($archive_path);
    my %in_archive = map { $_ => 1 } @$entries;
    my $targets = migration_targets_for_include($include);

    my @rows;
    for my $dst (@$targets) {
        my $rel = migration_rel_from_abs($dst);
        my $present = ($rel && $in_archive{$rel}) ? 1 : 0;
        my $exists = (-e $dst) ? 1 : 0;
        push @rows, {
            path      => $dst,
            in_archive=> $present,
            exists    => $exists,
            action    => ($present ? 'restore' : 'skip'),
            backup    => ($present && $exists) ? 1 : 0,
        };
    }
    return \@rows;
}

sub action_migration {
    my $dir = migration_dir();
    my $restore_preview_rows;
    my $restore_preview_file = '';

    my $do = $in{'mig_do'} || '';
    if ($do eq 'job_log') {
        my $job = $in{'job'} || '';
        if ($job !~ /^migration_[A-Za-z0-9_.\\-]+\\.log$/) {
            print &ui_print_error(L("ERR_MIG_JOB_LOG_INVALID"));
            return;
        }
        my $log = zfsguru_read_job_log(file => $job);
        if (!$log) {
            print &ui_print_error(L("ERR_JOB_LOG_NOT_FOUND"));
            return;
        }
        print &ui_subheading(L("SUB_MIG_JOB_LOG", &html_escape($job)));
        print "<p><a class='button' href='system.cgi?action=migration'>" . L("BTN_BACK") . "</a></p>";
        print "<pre class='zfsguru-code-block'>" . &html_escape($log) . "</pre>";
        return;
    }
    elsif ($do eq 'job_kill') {
        my $job = $in{'job'} || '';
        if ($job !~ /^migration_[A-Za-z0-9_.\\-]+\\.log$/) {
            print &ui_print_error(L("ERR_MIG_JOB_LOG_INVALID"));
            return;
        }
        my ($ok, $msg) = zfsguru_kill_job(file => $job);
        if ($ok) {
            print &ui_print_success(L("SUCCESS_JOB_KILLED", $msg));
        } else {
            print &ui_print_error(L("ERR_JOB_KILL_FAILED", $msg));
        }
    }

    if ($in{'upload_mig_archive'}) {
        my ($tmp, $orig) = update_get_upload('mig_archive_file');
        if (!$tmp) {
            print &ui_print_error(L("ERR_MIG_UPLOAD_NO_FILE"));
        } else {
            eval { update_ensure_dir($dir); };
            if ($@) {
                print &ui_print_error(L("ERR_MIG_DIR_INVALID", $@));
            } else {
                my $ts = strftime("%Y%m%d-%H%M%S", localtime());
                my $safe = update_sanitize_filename($orig || 'migration.tgz');
                my $saved_file = "zfsguru_migration_${ts}.tgz";
                my $saved = "$dir/$saved_file";
                eval {
                    update_copy_file_bin($tmp, $saved);
                    unlink($tmp);
                };
                if ($@) {
                    print &ui_print_error(L("ERR_MIG_UPLOAD_SAVE_FAILED", $@));
                } else {
                    print &ui_print_success(L("SUCCESS_MIG_UPLOAD_SAVED", $safe, $saved_file));
                }
            }
        }
    }

    if ($in{'preview_mig_restore'}) {
        my $file = $in{'mig_restore_file'} || '';
        my @include;
        push @include, 'module'   if $in{'mig_restore_module'};
        push @include, 'rc'       if $in{'mig_restore_rc'};
        push @include, 'sharing'  if $in{'mig_restore_sharing'};
        push @include, 'network'  if $in{'mig_restore_network'};

        if (!$file || $file !~ /^zfsguru_migration_\d{8}-\d{6}\.tgz$/) {
            print &ui_print_error(L("ERR_MIG_RESTORE_SELECT_ARCHIVE"));
        }
        elsif (!@include) {
            print &ui_print_error(L("ERR_MIG_RESTORE_SELECT_INCLUDE"));
        }
        else {
            my $path = "$dir/$file";
            if (!-r $path) {
                print &ui_print_error(L("ERR_MIG_RESTORE_ARCHIVE_NOT_FOUND", $file));
            } else {
                eval {
                    $restore_preview_rows = migration_build_restore_plan(
                        archive_path => $path,
                        include      => \@include,
                    );
                    $restore_preview_file = $file;
                };
                if ($@) {
                    print &ui_print_error(L("ERR_MIG_RESTORE_PREVIEW_FAILED", $@));
                } elsif ($restore_preview_rows && !@$restore_preview_rows) {
                    print &ui_alert(L("MSG_MIG_RESTORE_PREVIEW_EMPTY"), "info");
                } else {
                    print &ui_print_success(L("SUCCESS_MIG_RESTORE_PREVIEW_READY", $file));
                }
            }
        }
    }

    if ($in{'start_mig_export'}) {
        my @include;
        push @include, 'module'   if $in{'mig_include_module'};
        push @include, 'rc'       if $in{'mig_include_rc'};
        push @include, 'sharing'  if $in{'mig_include_sharing'};
        push @include, 'network'  if $in{'mig_include_network'};

        if (!@include) {
            print &ui_print_error(L("ERR_MIG_EXPORT_SELECT_INCLUDE"));
        }
        elsif (!$in{'confirm_mig_export'}) {
            print &ui_alert(L("WARN_MIG_EXPORT_SENSITIVE"), 'warning');
            print &ui_print_error(L("ERR_MIG_EXPORT_CONFIRM_REQUIRED"));
        }
        else {
            my $ts = strftime("%Y%m%d-%H%M%S", localtime());
            my $archive = "zfsguru_migration_${ts}.tgz";
            my $archive_path = "$dir/$archive";

            my @abs;
            if (grep { $_ eq 'module' } @include) {
                push @abs, "$config_directory/config" if $config_directory && $config_directory =~ m{^/};
            }
            if (grep { $_ eq 'rc' } @include) {
                push @abs, qw(/etc/rc.conf /boot/loader.conf /boot/loader.conf.local /etc/sysctl.conf /etc/fstab /etc/pf.conf);
            }
            if (grep { $_ eq 'sharing' } @include) {
                push @abs, qw(/etc/exports /usr/local/etc/smb4.conf /etc/ctl.conf /etc/ssh/sshd_config);
            }
            if (grep { $_ eq 'network' } @include) {
                push @abs, qw(/etc/hosts /etc/resolv.conf);
            }

            my $title = L("JOB_TITLE_MIG_EXPORT", $archive);
            my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                prefix => 'migration',
                title  => $title,
                run    => sub {
                    my $tar = $zfsguru_lib::TAR || '/usr/bin/tar';
                    if (!-d $dir) {
                        mkdir $dir or die "mkdir $dir failed: $!";
                    }

                    print "Export archive: $archive_path\n";
                    print "Include groups: " . join(', ', @include) . "\n";
                    print "\n";

                    my @rel;
                    for my $p (@abs) {
                        next unless defined $p && length $p;
                        if (!-e $p) {
                            print "SKIP (missing): $p\n";
                            next;
                        }
                        (my $r = $p) =~ s{^/}{};
                        push @rel, $r;
                        print "ADD: $p\n";
                    }
                    die "No files selected or found" unless @rel;

                    print "\nCreating archive...\n";
                    my @cmd = ($tar, 'czf', $archive_path, '-C', '/', @rel);
                    print ">> " . join(' ', @cmd) . "\n";
                    my $rc = system(@cmd);
                    if ($rc != 0) {
                        my $exit = ($rc == -1) ? 127 : ($rc >> 8);
                        die "tar failed rc=$exit";
                    }
                },
            );

            if (!$ok) {
                print &ui_print_error(L("ERR_MIG_EXPORT_JOB_START_FAILED", $err));
            } else {
                my $link = "system.cgi?action=migration&mig_do=job_log&job=" . &url_encode($log_file);
                print &ui_print_success(L("SUCCESS_MIG_EXPORT_JOB_STARTED", $job_id) . " " . &ui_link($link, L("BTN_VIEW_LOG")));
            }
        }
    }

    if ($in{'start_mig_restore'}) {
        my $file = $in{'mig_restore_file'} || '';
        if (!$file || $file !~ /^zfsguru_migration_\d{8}-\d{6}\.tgz$/) {
            print &ui_print_error(L("ERR_MIG_RESTORE_SELECT_ARCHIVE"));
        } else {
            my $path = "$dir/$file";
            my @include;
            push @include, 'module'   if $in{'mig_restore_module'};
            push @include, 'rc'       if $in{'mig_restore_rc'};
            push @include, 'sharing'  if $in{'mig_restore_sharing'};
            push @include, 'network'  if $in{'mig_restore_network'};

            if (!-r $path) {
                print &ui_print_error(L("ERR_MIG_RESTORE_ARCHIVE_NOT_FOUND", $file));
            }
            elsif (!@include) {
                print &ui_print_error(L("ERR_MIG_RESTORE_SELECT_INCLUDE"));
            }
            elsif (!$in{'confirm_mig_restore'}) {
                print &ui_alert(L("WARN_MIG_RESTORE_DANGEROUS"), 'warning');
                print &ui_print_error(L("ERR_MIG_RESTORE_CONFIRM_REQUIRED"));
            }
            elsif (!$in{'confirm_mig_restore_backup'}) {
                print &ui_alert(L("WARN_MIG_RESTORE_BACKUP"), 'warning');
                print &ui_print_error(L("ERR_MIG_RESTORE_CONFIRM_BACKUP_REQUIRED"));
            }
            elsif ((grep { $_ eq 'rc' } @include) && !$in{'confirm_mig_restore_boot'}) {
                print &ui_alert(L("WARN_MIG_RESTORE_BOOT"), 'warning');
                print &ui_print_error(L("ERR_MIG_RESTORE_CONFIRM_BOOT_REQUIRED"));
            }
            else {
                my $stamp = time . "_" . $$ . "_" . int(rand(1000));
                my $backup_dir = "$dir/restore_backup_$stamp";
                my $title = L("JOB_TITLE_MIG_RESTORE", $file);
                my ($ok, $job_id, $log_file, $err) = zfsguru_start_job(
                    prefix => 'migration',
                    title  => $title,
                    run    => sub {
                        migration_restore_archive(
                            archive_path => $path,
                            include      => \@include,
                            backup_dir   => $backup_dir,
                        );
                    },
                );

                if (!$ok) {
                    print &ui_print_error(L("ERR_MIG_RESTORE_JOB_START_FAILED", $err));
                } else {
                    my $link = "system.cgi?action=migration&mig_do=job_log&job=" . &url_encode($log_file);
                    print &ui_print_success(L("SUCCESS_MIG_RESTORE_JOB_STARTED", $job_id) . " " . &ui_link($link, L("BTN_VIEW_LOG")));
                }
            }
        }
    }

    print &ui_subheading(L("SUB_SYS_MIGRATION"));
    print "<p>" . L("MSG_SYS_MIGRATION_INTRO") . "</p>";

    print &ui_subheading(L("SUB_SYS_MIGRATION_EXPORT"));
    print &ui_form_start("system.cgi", "post");
    print &ui_hidden("action", "migration");
    print &ui_hidden("start_mig_export", 1);

    print &ui_table_start(L("TABLE_SYS_MIGRATION_EXPORT"), "width=100%", 2);
    my $opts = join("<br>",
        &ui_checkbox("mig_include_module", 1, L("OPT_MIG_EXPORT_MODULE"), ($in{'mig_include_module'} || !$in{'start_mig_export'}) ? 1 : 0),
        &ui_checkbox("mig_include_rc", 1, L("OPT_MIG_EXPORT_RC"), $in{'mig_include_rc'} ? 1 : 0),
        &ui_checkbox("mig_include_sharing", 1, L("OPT_MIG_EXPORT_SHARING"), $in{'mig_include_sharing'} ? 1 : 0),
        &ui_checkbox("mig_include_network", 1, L("OPT_MIG_EXPORT_NETWORK"), $in{'mig_include_network'} ? 1 : 0),
    );
    print &ui_table_row(L("ROW_MIGRATION_EXPORT_INCLUDE"), $opts);
    print &ui_table_row(
        L("ROW_MIGRATION_CONFIRM"),
        &ui_checkbox("confirm_mig_export", 1, L("LBL_CONFIRM_MIGRATION_EXPORT"), 0)
    );
    print &ui_table_end();

    print &ui_form_end([ [ "start_mig_export", L("BTN_MIGRATION_EXPORT") ] ]);

    print &ui_subheading(L("SUB_SYS_MIGRATION_JOBS"));
    print "<p>" . L("MSG_SYS_MIGRATION_JOBS") . "</p>";
    my $jobs = zfsguru_list_jobs(prefix => 'migration');
    my @jheads = (L("COL_JOB"), L("COL_STATUS"), L("COL_UPDATED"), L("COL_ACTIONS"));
    my @jdata;
    for my $j (@{ $jobs || [] }) {
        my $f = $j->{file} || next;
        my $view = "system.cgi?action=migration&mig_do=job_log&job=" . &url_encode($f);
        my $st_raw = $j->{status} || '';
        my $view_btn = "<a class='button' style='background:#0275d8;color:#fff;border-color:#0275d8' href='" . &html_escape($view) . "'>"
                     . &html_escape(L("BTN_VIEW_LOG"))
                     . "</a>";
        my $kill_btn = '';
        if ($st_raw eq 'running') {
            $kill_btn = "<form method='post' action='system.cgi' style='display:inline;margin-left:6px'>"
                      . &ui_hidden("action", "migration")
                      . &ui_hidden("mig_do", "job_kill")
                      . &ui_hidden("job", $f)
                      . "<input type='submit' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                      . "' style='background:#d9534f;color:#fff;border-color:#d9534f'>"
                      . "</form>";
        } else {
            $kill_btn = "<input type='button' class='ui_submit' value='" . &html_escape(L("BTN_KILL_JOB"))
                      . "' disabled='disabled' title='" . &html_escape(L("MSG_JOB_NOT_RUNNING"))
                      . "' style='margin-left:6px;background:#d9534f;color:#fff;border-color:#d9534f;opacity:.45;cursor:not-allowed'>";
        }
        push @jdata, [
            &html_escape($f),
            &html_escape($j->{status} || ''),
            &html_escape($j->{mtime} || ''),
            $view_btn . $kill_btn,
        ];
    }
    print &ui_columns_table(\@jheads, 100, \@jdata, undef, 1, L("TABLE_SYS_MIGRATION_JOBS"), L("VALUE_NONE"));

    print &ui_subheading(L("SUB_SYS_MIGRATION_ARCHIVES"));
    my $archives = list_migration_archives();
    if (!$archives || !@$archives) {
        print &ui_alert(L("MSG_MIG_NO_ARCHIVES_YET"), 'info');
    }
    my $restore_default = $in{'restore_file'} || $in{'mig_restore_file'} || '';
    my @aheads = (L("COL_FILE"), L("COL_SIZE"), L("COL_MODIFIED"), L("COL_ACTIONS"));
    my @adata;
    for my $a (@{ $archives || [] }) {
        my $f = $a->{file} || next;
        my $dl = "system.cgi?action=migration&mig_do=download&file=" . &url_encode($f);
        my $rs = "system.cgi?action=migration&restore_file=" . &url_encode($f);
        push @adata, [
            &html_escape($f),
            &html_escape($a->{size} || ''),
            &html_escape($a->{mtime} || ''),
            "<a class='button' href='" . &html_escape($dl) . "'>" . &html_escape(L("BTN_DOWNLOAD")) . "</a> " .
            "<a class='button' href='" . &html_escape($rs) . "'>" . &html_escape(L("BTN_MIGRATION_RESTORE")) . "</a>",
        ];
    }
    print &ui_columns_table(\@aheads, 100, \@adata, undef, 1, L("TABLE_SYS_MIGRATION_ARCHIVES"), L("VALUE_NONE"));

    print &ui_hr();
    print &ui_subheading(L("SUB_SYS_MIGRATION_UPLOAD"));
    print "<p>" . L("MSG_SYS_MIGRATION_UPLOAD_NOTE") . "</p>";
    print &ui_form_start("system.cgi", "form-data");
    print &ui_hidden("action", "migration");
    print &ui_hidden("upload_mig_archive", 1);
    print &ui_table_start(L("TABLE_SYS_MIGRATION_UPLOAD"), "width=100%", 2);
    print &ui_table_row(L("ROW_MIGRATION_UPLOAD_FILE"), &ui_upload("mig_archive_file", 60));
    print &ui_table_end();
    print &ui_form_end([ [ "upload_mig_archive", L("BTN_MIGRATION_UPLOAD") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_SYS_MIGRATION_RESTORE"));
    print &ui_alert(L("WARN_MIG_RESTORE_DANGEROUS"), 'warning');
    print &ui_alert(L("WARN_MIG_RESTORE_BACKUP"), 'info');

    if ($restore_preview_rows) {
        print &ui_subheading(L("SUB_SYS_MIGRATION_RESTORE_PREVIEW", &html_escape($restore_preview_file)));
        my @pheads = (
            L("COL_PATH"),
            L("COL_MIG_IN_ARCHIVE"),
            L("COL_ACTION"),
            L("COL_MIG_BACKUP"),
        );
        my @pdata;
        for my $r (@$restore_preview_rows) {
            push @pdata, [
                &html_escape($r->{path} || ''),
                ($r->{in_archive} ? L("VALUE_YES") : L("VALUE_NO")),
                ($r->{action} eq 'restore' ? L("VALUE_MIG_RESTORE") : L("VALUE_MIG_SKIP")),
                ($r->{backup} ? L("VALUE_YES") : L("VALUE_NO")),
            ];
        }
        print &ui_columns_table(\@pheads, 100, \@pdata, undef, 1,
            L("TABLE_SYS_MIGRATION_RESTORE_PREVIEW"), L("VALUE_NONE"));
    }

    print &ui_form_start("system.cgi", "post");
    print &ui_hidden("action", "migration");

    my @files_opt = map { [ $_->{file}, $_->{file} ] } @{ $archives || [] };
    unshift @files_opt, [ '', '-' ];

    print &ui_table_start(L("TABLE_SYS_MIGRATION_RESTORE"), "width=100%", 2);
    print &ui_table_row(L("ROW_MIG_RESTORE_ARCHIVE"), &ui_select("mig_restore_file", $restore_default, \@files_opt));

    my $restore_opts = join("<br>",
        &ui_checkbox("mig_restore_module", 1, L("OPT_MIG_EXPORT_MODULE"), ($in{'mig_restore_module'} || !$in{'start_mig_restore'}) ? 1 : 0),
        &ui_checkbox("mig_restore_rc", 1, L("OPT_MIG_EXPORT_RC"), $in{'mig_restore_rc'} ? 1 : 0),
        &ui_checkbox("mig_restore_sharing", 1, L("OPT_MIG_EXPORT_SHARING"), $in{'mig_restore_sharing'} ? 1 : 0),
        &ui_checkbox("mig_restore_network", 1, L("OPT_MIG_EXPORT_NETWORK"), $in{'mig_restore_network'} ? 1 : 0),
    );
    print &ui_table_row(L("ROW_MIGRATION_EXPORT_INCLUDE"), $restore_opts);

    print &ui_table_row(
        L("ROW_MIGRATION_CONFIRM"),
        &ui_checkbox("confirm_mig_restore", 1, L("LBL_CONFIRM_MIGRATION_RESTORE"), 0)
    );
    print &ui_table_row(
        L("ROW_MIGRATION_CONFIRM_BACKUP"),
        &ui_checkbox("confirm_mig_restore_backup", 1, L("LBL_CONFIRM_MIGRATION_RESTORE_BACKUP"), 0) .
        "<br><small>" . L("HINT_MIGRATION_CONFIRM_BACKUP", &html_escape($dir)) . "</small>"
    );
    print &ui_table_row(
        L("ROW_MIGRATION_CONFIRM_BOOT"),
        &ui_checkbox("confirm_mig_restore_boot", 1, L("LBL_CONFIRM_MIGRATION_RESTORE_BOOT"), 0) .
        "<br><small>" . L("HINT_MIGRATION_CONFIRM_BOOT") . "</small>"
    );
    print &ui_table_end();

    print &ui_form_end([
        [ "preview_mig_restore", L("BTN_MIGRATION_PREVIEW") ],
        [ "start_mig_restore",   L("BTN_MIGRATION_RESTORE") ],
    ]);
}

sub zfs_dataset_type {
    my ($dataset) = @_;
    return '' unless defined $dataset && is_dataset_name($dataset);
    my $rows = zfs_get($dataset, 'type');
    return '' unless $rows && ref($rows) eq 'HASH';
    my $t = $rows->{type};
    return '' unless defined $t && length $t;
    return lc($t);
}

sub sysctl_value {
    my ($key) = @_;
    return undef unless defined $key && length $key;
    my $cmd = $zfsguru_lib::SYSCTL || '/sbin/sysctl';
    my ($rc, $out, $err) = run_cmd($cmd, '-n', $key);
    return undef if $rc != 0;
    chomp $out;
    return $out;
}

sub bytes_to_human {
    my ($bytes) = @_;
    return L("VALUE_UNKNOWN") unless defined $bytes && $bytes =~ /^\d+$/;
    my $b = $bytes + 0;
    my @u = ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB');
    my $i = 0;
    while ($b >= 1024 && $i < $#u) {
        $b /= 1024;
        $i++;
    }
    my $s = ($i == 0) ? sprintf("%d", $b) : sprintf("%.1f", $b);
    $s =~ s/\.0$//;
    return $s . " " . $u[$i];
}

sub loaderconf_profiles {
    return {
        none => {
            static => {
                'vm.kmem_size'            => undef,
                'vfs.zfs.arc_max'         => undef,
                'vfs.zfs.arc_min'         => undef,
                'vfs.zfs.prefetch_disable'=> undef,
            },
        },
        minimal => {
            multiply => {
                'vm.kmem_size'    => 1.5,
                'vfs.zfs.arc_max' => 0.1,
                'vfs.zfs.arc_min' => 0.1,
            },
        },
        conservative => {
            multiply => {
                'vm.kmem_size'    => 1.5,
                'vfs.zfs.arc_max' => 0.3,
                'vfs.zfs.arc_min' => 0.2,
            },
        },
        balanced => {
            multiply => {
                'vm.kmem_size'    => 1.5,
                'vfs.zfs.arc_max' => 0.5,
                'vfs.zfs.arc_min' => 0.2,
            },
        },
        performance => {
            multiply => {
                'vm.kmem_size'    => 1.5,
                'vfs.zfs.arc_max' => 0.6,
                'vfs.zfs.arc_min' => 0.4,
            },
            static => {
                'vfs.zfs.prefetch_disable' => '0',
            },
        },
        aggressive => {
            multiply => {
                'vm.kmem_size'    => 1.5,
                'vfs.zfs.arc_max' => 0.75,
                'vfs.zfs.arc_min' => 0.5,
            },
            static => {
                'vfs.zfs.prefetch_disable' => '0',
            },
        },
    };
}

sub loaderconf_profile_settings {
    my ($profile, $physmem_bytes) = @_;
    my $profiles = loaderconf_profiles();
    die "Unknown profile" unless $profiles->{$profile};
    die "Invalid hw.physmem" unless defined $physmem_bytes && $physmem_bytes =~ /^\d+$/;

    my $physmem_gib = ($physmem_bytes / (1024 * 1024 * 1024));
    my $physmem_gib_round = sprintf("%.1f", $physmem_gib);
    $physmem_gib_round =~ s/\.0$//;
    my $p = $profiles->{$profile};
    my %out;

    if ($p->{multiply}) {
        for my $k (keys %{ $p->{multiply} }) {
            my $factor = $p->{multiply}{$k};
            my $v = ($physmem_gib * $factor);
            my $s = sprintf("%.1f", $v);
            $s =~ s/\.0$//;
            $out{$k} = { enabled => 1, value => $s . 'g' };
        }
    }

    if ($p->{static}) {
        for my $k (keys %{ $p->{static} }) {
            my $v = $p->{static}{$k};
            if (!defined $v) {
                $out{$k} = { enabled => 0, value => '' };
            } else {
                $out{$k} = { enabled => 1, value => $v };
            }
        }
    }

    return \%out;
}

sub loaderconf_detect_profile {
    my ($settings, $physmem_bytes) = @_;
    return '' unless ref($settings) eq 'HASH';
    return '' unless defined $physmem_bytes && $physmem_bytes =~ /^\d+$/;
    my $profiles = loaderconf_profiles();

    for my $name (sort keys %$profiles) {
        my $expected = loaderconf_profile_settings($name, $physmem_bytes);
        my $ok = 1;
        for my $k (keys %$expected) {
            my $want = $expected->{$k};
            my $cur = $settings->{$k} || { enabled => 0, value => '' };
            if ($want->{enabled}) {
                if (!$cur->{enabled}) { $ok = 0; last; }
                if (($cur->{value} // '') ne ($want->{value} // '')) { $ok = 0; last; }
            } else {
                if ($cur->{enabled}) { $ok = 0; last; }
            }
        }
        return $name if $ok;
    }

    return '';
}

sub loaderconf_parse {
    my ($raw) = @_;
    $raw = '' unless defined $raw;
    my %vars;
    for my $line (split /\n/, $raw) {
        $line =~ s/\r$//;
        next unless $line =~ /\S/;
        my $enabled = 1;
        my $work = $line;
        if ($work =~ /^\s*#/) {
            $enabled = 0;
            $work =~ s/^\s*#\s*//;
        }
        next if $work =~ /^\s*#/;
        next unless $work =~ /^\s*([A-Za-z0-9._-]+)\s*=\s*(.*?)\s*$/;
        my ($k, $vraw) = ($1, $2);
        next unless length $k;
        $vraw =~ s/\s*(?:#.*)?$//;
        $vraw =~ s/^\s+|\s+$//g;
        my $v = $vraw;
        if ($v =~ /^"(.*)"$/) {
            $v = $1;
        } elsif ($v =~ /^'(.*)'$/) {
            $v = $1;
        }
        $vars{$k} = { enabled => $enabled ? 1 : 0, value => $v };
    }

    # Ensure key vars exist for profiles and common tuning lists.
    for my $k (qw(vm.kmem_size vfs.zfs.arc_max vfs.zfs.arc_min vfs.zfs.prefetch_disable)) {
        $vars{$k} ||= { enabled => 0, value => '' };
    }
    for my $e (loaderconf_zfs_tuning_vars()) {
        my $k = $e->{name};
        $vars{$k} ||= { enabled => 0, value => '' };
    }
    return \%vars;
}

sub loaderconf_quote_value {
    my ($v) = @_;
    $v = '' unless defined $v;
    $v =~ s/[\r\n]//g;
    $v =~ s/\"/\\\"/g;
    return '"' . $v . '"';
}

sub loaderconf_update_file {
    my ($path, $new) = @_;
    die "Invalid path" unless defined $path && $path =~ m{^/};
    die "Invalid settings" unless ref($new) eq 'HASH';

    my $raw = read_file_text($path);
    $raw = '' unless defined $raw;

    for my $k (sort keys %$new) {
        next unless defined $k && $k =~ /^[A-Za-z0-9._-]+$/;
        my $data = $new->{$k} || {};
        my $enabled = $data->{enabled} ? 1 : 0;
        my $val = defined $data->{value} ? $data->{value} : '';
        my $quoted = loaderconf_quote_value($val);
        my $line_on  = $k . '=' . $quoted;
        my $line_off = '#' . $k . '=' . $quoted;

        if ($raw =~ /^\s*\Q$k\E\s*=/m) {
            my $rep = $enabled ? $line_on : $line_off;
            $raw =~ s/^\s*\Q$k\E\s*=.*$/$rep/m;
            next;
        }
        if ($raw =~ /^\s*#\s*\Q$k\E\s*=/m) {
            my $rep = $enabled ? $line_on : $line_off;
            $raw =~ s/^\s*#\s*\Q$k\E\s*=.*$/$rep/m;
            next;
        }

        next unless $enabled;
        $raw .= "\n" if length($raw) && $raw !~ /\n\z/;
        $raw .= "# added by ZFSguru\n" . $line_on . "\n";
    }

    my $backup = write_file_with_backup($path, $raw);
    eval { run_cmd($zfsguru_lib::CHOWN || '/usr/sbin/chown', 'root:wheel', $path); };
    eval { run_cmd($zfsguru_lib::CHMOD || '/bin/chmod', '644', $path); };
    return $backup;
}

sub loaderconf_zfs_tuning_vars {
    return (
        { name => 'vfs.zfs.arc_min', desc => L('DESC_TUNING_ARC_MIN'), recommended => L('REC_TUNING_ARC_MIN') },
        { name => 'vfs.zfs.arc_max', desc => L('DESC_TUNING_ARC_MAX'), recommended => L('REC_TUNING_ARC_MAX') },
        { name => 'vfs.zfs.arc_meta_limit', desc => L('DESC_TUNING_ARC_META_LIMIT'), recommended => L('REC_TUNING_ARC_META_LIMIT') },
        { name => 'vfs.zfs.prefetch_disable', desc => L('DESC_TUNING_PREFETCH_DISABLE'), recommended => L('REC_TUNING_PREFETCH_DISABLE') },
        { name => 'vfs.zfs.vdev.min_pending', desc => L('DESC_TUNING_VDEV_MIN_PENDING'), recommended => L('REC_TUNING_VDEV_MIN_PENDING') },
        { name => 'vfs.zfs.vdev.max_pending', desc => L('DESC_TUNING_VDEV_MAX_PENDING'), recommended => L('REC_TUNING_VDEV_MAX_PENDING') },
        { name => 'vfs.zfs.txg.synctime', desc => L('DESC_TUNING_TXG_SYNCTIME'), recommended => L('REC_TUNING_TXG_SYNCTIME') },
        { name => 'vfs.zfs.txg.timeout', desc => L('DESC_TUNING_TXG_TIMEOUT'), recommended => L('REC_TUNING_TXG_TIMEOUT') },
        { name => 'vfs.zfs.txg.write_limit_override', desc => L('DESC_TUNING_TXG_WRITE_LIMIT_OVERRIDE'), recommended => L('REC_TUNING_TXG_WRITE_LIMIT_OVERRIDE') },
        { name => 'vfs.zfs.cache_flush_disable', desc => L('DESC_TUNING_CACHE_FLUSH_DISABLE'), recommended => L('REC_TUNING_CACHE_FLUSH_DISABLE') },
        { name => 'vfs.zfs.zil_disable', desc => L('DESC_TUNING_ZIL_DISABLE'), recommended => L('REC_TUNING_ZIL_DISABLE') },
    );
}

sub loaderconf_var_description {
    my ($var) = @_;
    return '' unless defined $var && length $var;
    my %zdesc = map { ($_->{name} => $_->{desc}) } loaderconf_zfs_tuning_vars();
    return $zdesc{$var} if exists $zdesc{$var};
    return L('DESC_TUNING_KMEM_SIZE') if $var eq 'vm.kmem_size';
    return L('DESC_TUNING_KMEM_SIZE_MAX') if $var eq 'vm.kmem_size_max';
    return L('DESC_TUNING_ZFS_LOAD') if $var eq 'zfs_load';
    return L('DESC_TUNING_OPENSOLARIS_LOAD') if $var eq 'opensolaris_load';
    return L('DESC_TUNING_GEOM_ELI_LOAD') if $var eq 'geom_eli_load';
    return L('DESC_TUNING_AHCI_LOAD') if $var eq 'ahci_load';
    return L('DESC_TUNING_VFS_ROOT_MOUNTFROM') if $var eq 'vfs.root.mountfrom';
    return L('DESC_TUNING_AUTOBOOT_DELAY') if $var eq 'autoboot_delay';
    return L('DESC_TUNING_BEASTIE_DISABLE') if $var eq 'beastie_disable';
    return L('DESC_TUNING_BOOT_MULTICONS') if $var eq 'boot_multicons';
    return L('DESC_TUNING_CONSOLE') if $var eq 'console';
    return L('DESC_TUNING_CAM_BOOT_DELAY') if $var eq 'kern.cam.boot_delay';
    return L('DESC_TUNING_GEOM_LABEL_DISK_IDENT_ENABLE') if $var eq 'kern.geom.label.disk_ident.enable';
    return L('DESC_TUNING_GEOM_LABEL_GPTID_ENABLE') if $var eq 'kern.geom.label.gptid.enable';
    return L('DESC_TUNING_IPC_NMBCLUSTERS') if $var eq 'kern.ipc.nmbclusters';
    return L('DESC_TUNING_DEBUG_DDB_TEXTDUMP_PENDING') if $var eq 'debug.ddb.textdump.pending';
    return L('DESC_TUNING_DUMPDEV') if $var eq 'dumpdev';
    return L('DESC_TUNING_IFCONFIG_DEFAULT') if $var eq 'ifconfig_DEFAULT';
    return L('DESC_TUNING_IPV6_ACTIVATE_ALL_INTERFACES') if $var eq 'ipv6_activate_all_interfaces';
    return L('DESC_TUNING_BACKGROUND_FSCK') if $var eq 'background_fsck';
    return L('DESC_TUNING_PERFORMANCE_CPUTYPE') if $var eq 'performance_cputype';
    return L('DESC_TUNING_CLEAR_TMP_ENABLE') if $var eq 'clear_tmp_enable';
    return L('DESC_TUNING_SSD_FLAGS') if $var eq 'vfs.zfs.vdev.trim_on_init';
    return L('DESC_TUNING_LOADER_MODULE') if $var =~ /_load$/;
    return L('DESC_TUNING_LOADER_HINT') if $var =~ /^hint\./;
    return L('DESC_TUNING_GENERIC');
}

sub update_get_upload {
    my ($field) = @_;
    my $tmp = $in{$field};
    my $orig = $in{$field . '_filename'} || '';

    if (ref($tmp) eq 'HASH') {
        $orig ||= $tmp->{filename} || '';
        $tmp = $tmp->{tmp} || $tmp->{temp} || $tmp->{file} || $tmp->{path} || '';
    }

    $tmp = '' if !defined $tmp;
    $orig = '' if !defined $orig;
    $orig =~ s{^.*[\\/]}{};

    return (undef, undef) unless length($tmp) && -r $tmp;
    return ($tmp, $orig);
}

sub update_ensure_dir {
    my ($dir) = @_;
    die "Invalid dir" unless defined $dir && length $dir;
    die "Upload dir must be absolute" unless $dir =~ m{^/};
    return 1 if -d $dir;

    my @parts = grep { length $_ } split m{/+}, $dir;
    my $cur = '';
    for my $p (@parts) {
        $cur .= "/$p";
        next if -d $cur;
        mkdir $cur or die "mkdir $cur failed: $!";
    }
    return 1;
}

sub update_sanitize_filename {
    my ($name) = @_;
    $name = '' unless defined $name;
    $name =~ s{^.*[\\/]}{};
    $name =~ s/[^A-Za-z0-9_.\\-]+/_/g;
    $name =~ s/^_+//;
    $name =~ s/_+$//;
    $name = 'upload.bin' if $name eq '';
    return $name;
}

sub update_copy_file_bin {
    my ($src, $dst) = @_;
    die "Missing src" unless defined $src && length $src;
    die "Missing dst" unless defined $dst && length $dst;

    open my $in_fh,  '<', $src or die "open src: $!";
    binmode($in_fh);
    open my $out_fh, '>', $dst or die "open dst: $!";
    binmode($out_fh);

    my $buf;
    while (1) {
        my $r = read($in_fh, $buf, 1024 * 1024);
        die "read failed: $!" unless defined $r;
        last if $r == 0;
        print $out_fh $buf or die "write failed: $!";
    }

    close $in_fh;
    close $out_fh;
    return 1;
}

sub update_find_packages {
    my ($dir) = @_;
    return () unless defined $dir && length $dir && -d $dir;
    my @out;
    my @stack = ($dir);
    while (@stack) {
        my $d = pop @stack;
        next unless -d $d;
        opendir my $dh, $d or next;
        my @ents = readdir $dh;
        closedir $dh;
        for my $e (@ents) {
            next if $e eq '.' || $e eq '..';
            my $p = "$d/$e";
            next if -l $p;
            if (-d $p) {
                push @stack, $p;
            } elsif (-f $p) {
                push @out, $p if $p =~ /\.(?:pkg|txz)\z/i;
            }
        }
    }
    @out = sort @out;
    return @out;
}

sub update_parse_pkg_list {
    my ($raw) = @_;
    $raw = '' unless defined $raw;
    $raw =~ s/\r//g;

    my @tokens = split(/\s+/, $raw);
    my (@pkgs, @bad);

    for my $t (@tokens) {
        next unless defined $t && length $t;

        $t =~ s/^[\"']+//;
        $t =~ s/[\"']+$//;
        $t =~ s/[,:;]+$//;

        next unless length $t;

        if ($t =~ /^-/ || $t !~ /^[A-Za-z0-9][A-Za-z0-9@\/._+\-]*$/) {
            push @bad, $t;
            next;
        }
        push @pkgs, $t;
    }

    # Dedupe while preserving order
    my %seen;
    @pkgs = grep { !$seen{$_}++ } @pkgs;

    return (\@pkgs, \@bad);
}

sub update_url_filename {
    my ($url) = @_;
    $url = '' unless defined $url;
    $url =~ s/[\r\n]//g;
    $url =~ s/[?#].*$//;     # drop query/fragment
    $url =~ s{^.*\/}{};      # basename
    return $url;
}

sub update_tar_entries_look_like_pkg {
    my ($entries) = @_;
    return 0 unless ref($entries) eq 'ARRAY';
    for my $e (@$entries) {
        next unless defined $e && length $e;
        return 1 if $e eq '+MANIFEST' || $e eq '+COMPACT_MANIFEST';
        return 1 if $e eq '+MANIFEST.gz' || $e eq '+COMPACT_MANIFEST.gz';
    }
    return 0;
}

sub update_offline_install_from_file {
    my ($saved, $workdir) = @_;
    $saved = '' unless defined $saved;
    $workdir = '' unless defined $workdir;

    print "Offline install file: $saved\n";
    print "Workdir: $workdir\n\n";

    my $pkg = $zfsguru_lib::PKG || '/usr/local/sbin/pkg';
    die "pkg command missing: $pkg" unless command_exists($pkg);

    my $tar = $zfsguru_lib::TAR || '/usr/bin/tar';
    if (!command_exists($tar)) {
        print "tar is missing ($tar). Treating as a single package file.\n";
        my $prc = system($pkg, 'add', '-f', $saved);
        die "pkg add failed" if $prc != 0;
        return 1;
    }

    my ($trc, $tout, $terr) = run_cmd($tar, 'tf', $saved);
    if ($trc == 0) {
        my @entries = grep { defined $_ && length $_ } split(/\n/, $tout || '');

        if (update_tar_entries_look_like_pkg(\@entries)) {
            print "Detected pkg archive (+MANIFEST). Installing directly.\n";
            my $prc = system($pkg, 'add', '-f', $saved);
            die "pkg add failed" if $prc != 0;
            return 1;
        }

        print "Detected tar archive. Validating entries ...\n";
        for my $e (@entries) {
            die "Unsafe archive entry: $e" if $e =~ m{^/} || $e =~ m{(^|/)\\.\\.(?:/|$)};
        }
        print "Extracting ...\n";
        my $rc = system($tar, 'xpf', $saved, '-C', $workdir);
        die "tar extract failed" if $rc != 0;

        my @pkgs = update_find_packages($workdir);
        die "No packages found in archive" unless @pkgs;
        print "Found packages:\n";
        print "  $_\n" for @pkgs;
        print "\nInstalling via pkg add ...\n";
        for my $p (@pkgs) {
            my $prc = system($pkg, 'add', '-f', $p);
            die "pkg add failed for $p" if $prc != 0;
        }
        return 1;
    }

    print "Not a tar archive. Treating as a single package file.\n";
    my $prc = system($pkg, 'add', '-f', $saved);
    die "pkg add failed" if $prc != 0;
    return 1;
}

sub prefcfg_file_path {
    return "$Bin/config.txt";
}

sub prefcfg_apply_updates {
    my ($updates) = @_;
    die "Invalid updates" unless ref($updates) eq 'HASH';
    my $cfg_file = prefcfg_file_path();
    my $raw = read_file_text($cfg_file);
    my ($order, $kv) = prefcfg_parse_config_kv($raw);

    my %merged = (%$kv, %$updates);
    my @val_errors = prefcfg_validate_config_values(\%merged);
    die join("\n", @val_errors) if @val_errors;

    my @ordered_names = @$order;
    my %seen = map { $_ => 1 } @ordered_names;
    for my $k (sort keys %$updates) {
        push @ordered_names, $k unless $seen{$k}++;
    }

    my $new_raw = prefcfg_rewrite_config_preserve_layout($raw, \%merged, \@ordered_names);
    my $backup = write_file_with_backup($cfg_file, $new_raw);

    for my $k (keys %$updates) {
        $config{$k} = $updates->{$k};
    }
    &save_module_config(\%config);
    return $backup;
}

sub prefcfg_parse_config_kv {
    my ($raw) = @_;
    my @order;
    my %kv;
    for my $line (split /\n/, ($raw || '')) {
        next if $line =~ /^\s*#/;
        next if $line !~ /\S/;
        next unless $line =~ /^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/;
        my ($k, $v) = ($1, $2);
        push @order, $k if !exists $kv{$k};
        $kv{$k} = $v;
    }
    return (\@order, \%kv);
}

sub prefcfg_group_config_keys {
    my ($order) = @_;
    $order = [] unless ref($order) eq 'ARRAY';
    my @group_order = (
        'Command Paths',
        'Logging',
        'UI Settings',
        'Advanced Options',
        'System Integration',
        'Security',
        'Performance',
        'Monitoring',
        'Backup/Snapshot defaults',
        'Legacy compatibility',
        'Other',
    );
    my %g;
    for my $k (@$order) {
        next unless defined $k && $k =~ /^[A-Za-z0-9_]+$/;
        my $cat = prefcfg_classify_config_key($k);
        push @{ $g{$cat} }, $k;
    }
    my @out;
    for my $name (@group_order) {
        push @out, { name => $name, keys => ($g{$name} || []) };
    }
    return \@out;
}

sub prefcfg_classify_config_key {
    my ($k) = @_;
    return 'Command Paths' if $k =~ /_cmd$/ || $k =~ /^ata_secure_erase_/;
    return 'Logging' if $k =~ /^(log_file|log_level)$/;
    return 'UI Settings' if $k =~ /^(theme|animation_effects|auto_refresh|auto_refresh_interval)$/;
    return 'Advanced Options' if $k =~ /^(advanced_mode|booting_expert_mode|enable_benchmarking|enable_smart_monitoring|enable_system_update_ui)$/;
    return 'System Integration' if $k =~ /^enable_(nfs|samba|ssh|iscsi)$/;
    return 'Security' if $k =~ /^require_confirmation_/;
    return 'Performance' if $k =~ /^(cache_pool_status|cache_dataset_list|cache_duration)$/;
    return 'Monitoring' if $k =~ /^monitor_/;
    return 'Backup/Snapshot defaults' if $k =~ /^default_/;
    return 'Legacy compatibility' if $k =~ /^(can_view|can_manage)$/;
    return 'Other';
}

sub prefcfg_validate_config_values {
    my ($vals) = @_;
    $vals = {} unless ref($vals) eq 'HASH';
    my @err;

    my %bool_keys = map { $_ => 1 } qw(
        animation_effects auto_refresh advanced_mode booting_expert_mode enable_benchmarking enable_smart_monitoring
        enable_system_update_ui enable_nfs enable_samba enable_ssh enable_iscsi
        require_confirmation_for_pool_create require_confirmation_for_disk_format require_confirmation_for_pool_export
        cache_pool_status cache_dataset_list can_view can_manage
    );
    for my $k (keys %$vals) {
        my $v = defined $vals->{$k} ? $vals->{$k} : '';
        if ($bool_keys{$k} && $v !~ /^[01]$/) {
            push @err, "$k must be 0 or 1";
        }
    }

    my %int_rules = (
        auto_refresh_interval => [0, 86400],
        cache_duration => [0, 86400],
        monitor_pool_capacity_threshold => [0, 100],
        monitor_alert_high_capacity => [0, 100],
        monitor_disk_temperature_warning => [0, 200],
        monitor_disk_temperature_critical => [0, 200],
        default_ashift => [9, 16],
    );
    for my $k (keys %int_rules) {
        next unless exists $vals->{$k};
        my $v = $vals->{$k};
        my ($min, $max) = @{ $int_rules{$k} };
        if ($v !~ /^\d+$/) {
            push @err, "$k must be an integer";
            next;
        }
        if ($v < $min || $v > $max) {
            push @err, "$k must be between $min and $max";
        }
    }

    if (exists $vals->{log_level}) {
        my $lv = lc($vals->{log_level} || '');
        if ($lv !~ /^(debug|info|warn|warning|error)$/) {
            push @err, "log_level must be one of: debug, info, warn, warning, error";
        }
    }

    for my $k (keys %$vals) {
        my $v = defined $vals->{$k} ? $vals->{$k} : '';
        if ($k =~ /_cmd$/ && length($v) && $v !~ m{^/}) {
            push @err, "$k must be an absolute path";
        }
    }

    if (exists $vals->{log_file} && length($vals->{log_file}) && $vals->{log_file} !~ m{^/}) {
        push @err, "log_file must be an absolute path";
    }

    return @err;
}

sub prefcfg_rewrite_config_preserve_layout {
    my ($raw, $newvals, $ordered_names) = @_;
    $raw = '' unless defined $raw;
    $newvals = {} unless ref($newvals) eq 'HASH';
    $ordered_names = [] unless ref($ordered_names) eq 'ARRAY';

    my @lines = split /\n/, $raw, -1;
    my %seen;
    for my $i (0 .. $#lines) {
        my $line = $lines[$i];
        next unless $line =~ /^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/;
        my $k = $1;
        next unless exists $newvals->{$k};
        my $v = defined $newvals->{$k} ? $newvals->{$k} : '';
        $v =~ s/\r//g;
        $v =~ s/\n/ /g;
        $lines[$i] = "$k=$v";
        $seen{$k} = 1;
    }

    my @append;
    for my $k (@$ordered_names) {
        next unless defined $k && $k =~ /^[A-Za-z0-9_]+$/;
        next if $seen{$k};
        my $v = defined $newvals->{$k} ? $newvals->{$k} : '';
        $v =~ s/\r//g;
        $v =~ s/\n/ /g;
        push @append, "$k=$v";
        $seen{$k} = 1;
    }

    if (@append) {
        push @lines, '' if @lines && $lines[-1] ne '';
        push @lines, '# Added via System Preferences UI';
        push @lines, @append;
    }

    my $out = join("\n", @lines);
    $out .= "\n" if $out !~ /\n\z/;
    return $out;
}

1;

