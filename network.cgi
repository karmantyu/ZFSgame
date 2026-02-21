#!/usr/bin/env perl

package main;

use strict;
use warnings;
use POSIX qw(strftime);
use File::Basename qw(basename);
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

zfsguru_readparse();
zfsguru_init('en');

my $RC_CONF      = '/etc/rc.conf';
my $RESOLV_CONF  = '/etc/resolv.conf';
my $DHCPD_CONF   = '/usr/local/etc/dhcpd.conf';
my $DNSMASQ_CONF = '/usr/local/etc/dnsmasq.conf';
my $INETD_CONF   = '/etc/inetd.conf';
my $TFTPBOOT_DIR = '/tftpboot';
my $CONFIG_BACKUP_DIR = '/var/tmp/zfsguru-config-backups';

zfsguru_page_header(title_key => "TITLE_NETWORK");

eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('network'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'network'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'interfaces';

my @tabs_list = (
    [ 'interfaces', 'TAB_NET_INTERFACES' ],
    [ 'networkquery', 'TAB_NET_NETWORKQUERY' ],
    [ 'ports',      'TAB_NET_PORTS' ],
    [ 'firewall',   'TAB_NET_FIREWALL' ],
    [ 'dns',        'TAB_NET_DNS' ],
    [ 'dhcp',       'TAB_NET_DHCP' ],
    [ 'dnsmasq',    'TAB_NET_DNSMASQ' ],
    [ 'lagg',       'TAB_NET_LAGG' ],
    [ 'pxe',        'TAB_NET_PXE' ],
);

print zfsguru_print_tabs(
    script => 'network.cgi',
    active => $action,
    tabs   => \@tabs_list,
);

if ($action eq 'interfaces') {
    action_interfaces();
} elsif ($action eq 'networkquery') {
    action_networkquery();
} elsif ($action eq 'ports') {
    action_ports();
} elsif ($action eq 'firewall') {
    action_firewall();
} elsif ($action eq 'dns') {
    action_dns();
} elsif ($action eq 'dhcp') {
    action_dhcp();
} elsif ($action eq 'dnsmasq') {
    action_dnsmasq();
} elsif ($action eq 'lagg') {
    action_lagg();
} elsif ($action eq 'pxe') {
    action_pxe();
}

my $back_url = 'index.cgi';
if ($action ne 'interfaces') {
    $back_url = 'network.cgi?action=interfaces';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_interfaces {
    my $ifs = normalized_network_interfaces_list();
    print &ui_subheading(L("SUB_NET_INTERFACES"));

    if (!@$ifs) {
        print &ui_print_error(L("ERR_NET_INTERFACES_FAILED"));
        return;
    }

    print &ui_table_start(L("TABLE_NET_INTERFACES"), "width=100%", 2, [
        L("COL_INTERFACE"), L("COL_IPV4"), L("COL_IPV6"), L("COL_STATUS"), L("COL_MTU"), L("COL_MAC")
    ]);

    for my $if (@$ifs) {
        print &ui_table_row(
            $if->{name},
            $if->{ipv4_text},
            $if->{ipv6_text},
            $if->{status},
            $if->{mtu},
            $if->{mac},
        );
    }
    print &ui_table_end();
}

sub action_networkquery {
    print &ui_subheading(L("SUB_NET_NETWORKQUERY"));
    print "<p>" . L("MSG_NET_NETWORKQUERY_NOTE") . "</p>";

    my $ifs = normalized_network_interfaces_list();
    if (!@$ifs) {
        print &ui_print_error(L("ERR_NET_INTERFACES_FAILED"));
        return;
    }

    my %by_name = map { $_->{name} => $_ } @$ifs;
    my $query_if = $in{'query'} || $in{'iface'} || '';
    if (!$query_if || !$by_name{$query_if}) {
        $query_if = $ifs->[0]{name} || '';
    }

    # Interface list with per-interface query links
    print &ui_table_start(L("TABLE_NET_QUERY_IFLIST"), "width=100%", 2, [
        L("COL_INTERFACE"), L("COL_IPV4"), L("COL_IPV6"), L("COL_STATUS"), L("COL_MTU"), L("COL_MAC")
    ]);
    for my $if (@$ifs) {
        my $name = $if->{name} || next;
        my $url = "network.cgi?action=networkquery&query=" . &url_encode($name);
        my $link = &ui_link($url, &html_escape($name), "zfsguru-link");
        my $name_html = ($name eq $query_if) ? "<b>$link</b>" : $link;
        print &ui_table_row(
            $name_html,
            $if->{ipv4_text},
            $if->{ipv6_text},
            $if->{status},
            $if->{mtu},
            $if->{mac},
        );
    }
    print &ui_table_end();

    return unless $query_if && $query_if =~ /^[A-Za-z0-9:_\\-\\.]+$/;

    my $detail;
    eval { $detail = normalized_network_interface_details($query_if); };
    if ($@ || !$detail) {
        my $err = $@;
        $err =~ s/\\s+$// if defined $err;
        print &ui_print_error(L("ERR_NET_QUERY_FAILED", $query_if, ($err || 'query failed')));
        return;
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_NET_QUERY_INTERFACE", $query_if));

    print &ui_table_start(L("TABLE_NET_QUERY"), "width=100%", 2);
    print &ui_table_row(L("ROW_NET_QUERY_IFNAME"), &html_escape($detail->{ifname} || $query_if));
    print &ui_table_row(L("ROW_NET_QUERY_IDENT"), &html_escape($detail->{ident} || '-'));
    print &ui_table_row(L("ROW_NET_QUERY_STATUS"), &html_escape($detail->{status} || '-'));
    print &ui_table_row(L("ROW_NET_QUERY_LINKSPEED"), &html_escape($detail->{linkspeed} || '-'));
    print &ui_table_row(L("ROW_NET_QUERY_FLAGS"), &html_escape($detail->{flags_str} || '-'));
    print &ui_table_row(L("ROW_NET_QUERY_CAPABILITIES"), &html_escape($detail->{options_str} || '-'));
    print &ui_table_row(L("ROW_NET_QUERY_MAC"), &html_escape($detail->{ether} || '-'));
    print &ui_table_row(L("ROW_NET_QUERY_MTU"), &html_escape($detail->{mtu} || '-'));
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_NET_QUERY_IPV4"));
    print &ui_table_start(L("TABLE_NET_QUERY_IPV4"), "width=100%", 2, [
        L("COL_NET_QUERY_IP"),
        L("COL_NET_QUERY_SUBNET"),
        L("COL_NET_QUERY_BROADCAST"),
    ]);
    if (@{ $detail->{inet} || [] }) {
        for my $ip (@{ $detail->{inet} }) {
            print &ui_table_row(
                &html_escape($ip->{ip} || '-'),
                &html_escape($ip->{subnet} || $ip->{netmask} || '-'),
                &html_escape($ip->{broadcast} || '-'),
            );
        }
    } else {
        print &ui_table_row("-", "-", "-");
    }
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_NET_QUERY_IPV6"));
    print &ui_table_start(L("TABLE_NET_QUERY_IPV6"), "width=100%", 2, [
        L("COL_NET_QUERY_IP"),
        L("COL_NET_QUERY_PREFIXLEN"),
        L("COL_NET_QUERY_SCOPE"),
    ]);
    if (@{ $detail->{inet6} || [] }) {
        for my $ip (@{ $detail->{inet6} }) {
            print &ui_table_row(
                &html_escape($ip->{ip} || '-'),
                &html_escape($ip->{prefixlen} || '-'),
                &html_escape($ip->{scopeid} || '-'),
            );
        }
    } else {
        print &ui_table_row("-", "-", "-");
    }
    print &ui_table_end();
}

sub action_ports {
    my $ports = network_listening_ports();
    print &ui_subheading(L("SUB_NET_PORTS"));

    if (!@$ports) {
        print &ui_print_error(L("ERR_NET_PORTS_FAILED"));
        return;
    }

    my @net_ports = grep {
        (($_->{protocol} || '') =~ /^(?:TCP|UDP)$/) &&
        (defined $_->{port} && $_->{port} =~ /^\d+$/)
    } @$ports;
    my $other_count = scalar(@$ports) - scalar(@net_ports);

    my ($tcp_count, $udp_count) = (0, 0);
    my %uniq_ports;
    my %by_cmd;
    for my $p (@net_ports) {
        my $proto = $p->{protocol};
        $tcp_count++ if $proto eq 'TCP';
        $udp_count++ if $proto eq 'UDP';
        $uniq_ports{$p->{port}} = 1;
        my $cmd = $p->{command} || '-';
        $by_cmd{$cmd} ||= { users => {}, pids => {}, tcp => {}, udp => {}, rows => 0 };
        $by_cmd{$cmd}{rows}++;
        $by_cmd{$cmd}{users}{$p->{user} || '-'} = 1;
        $by_cmd{$cmd}{pids}{$p->{pid} || '-'} = 1;
        if ($proto eq 'TCP') {
            $by_cmd{$cmd}{tcp}{$p->{port}} = 1;
        } elsif ($proto eq 'UDP') {
            $by_cmd{$cmd}{udp}{$p->{port}} = 1;
        }
    }

    my @summary_cards;
    push @summary_cards, "<b>Total listeners</b><br>" . scalar(@$ports);
    push @summary_cards, "<b>Network listeners</b><br>" . scalar(@net_ports);
    push @summary_cards, "<b>TCP / UDP</b><br>$tcp_count / $udp_count";
    push @summary_cards, "<b>Unique ports</b><br>" . scalar(keys %uniq_ports);
    push @summary_cards, "<b>Other sockets</b><br>$other_count" if $other_count > 0;

    my $card_style = "border:1px solid #d8d8d8;background:#f9f9f9;padding:10px;border-radius:3px;line-height:1.4;min-height:88px";
    my $render_mosaic = sub {
        my ($cards, $cols) = @_;
        $cols ||= 4;
        return if !$cards || !@$cards;
        print "<table class='ui_table' style='width:100%;table-layout:fixed;border-collapse:separate;border-spacing:8px'>";
        my $i = 0;
        while ($i < scalar(@$cards)) {
            print "<tr>";
            for (my $c = 0; $c < $cols; $c++) {
                if ($i < scalar(@$cards)) {
                    print "<td style='vertical-align:top;width:" . int(100 / $cols) . "%'><div style='$card_style'>$cards->[$i]</div></td>";
                    $i++;
                } else {
                    print "<td style='vertical-align:top;width:" . int(100 / $cols) . "%'></td>";
                }
            }
            print "</tr>";
        }
        print "</table>";
    };

    print &ui_subheading("Port Summary");
    $render_mosaic->(\@summary_cards, 5);

    my @cmd_cards;
    for my $cmd (sort { lc($a) cmp lc($b) } keys %by_cmd) {
        my $r = $by_cmd{$cmd};
        my @users = sort keys %{ $r->{users} };
        my @pids  = sort { $a <=> $b } grep { /^\d+$/ } keys %{ $r->{pids} };
        my @tcp_ports = sort { $a <=> $b } keys %{ $r->{tcp} };
        my @udp_ports = sort { $a <=> $b } keys %{ $r->{udp} };
        my $tcp_txt = @tcp_ports ? join(', ', @tcp_ports) : '-';
        my $udp_txt = @udp_ports ? join(', ', @udp_ports) : '-';
        my $pid_txt = @pids ? join(', ', @pids) : '-';
        my $user_txt = @users ? join(', ', @users) : '-';
        push @cmd_cards,
            "<b>" . &html_escape($cmd) . "</b><br>" .
            "Listeners: " . int($r->{rows}) . "<br>" .
            "Users: " . &html_escape($user_txt) . "<br>" .
            "PIDs: " . &html_escape($pid_txt) . "<br>" .
            "TCP ports: " . &html_escape($tcp_txt) . "<br>" .
            "UDP ports: " . &html_escape($udp_txt);
    }
    print &ui_subheading("Listening Applications");
    $render_mosaic->(\@cmd_cards, 4);

    my %by_port;
    for my $p (@net_ports) {
        my $proto_disp = $p->{protocol} || ($p->{proto} || '-');
        if (($p->{protocol} || '') ne '-' && ($p->{ipver} || '') ne '') {
            $proto_disp .= $p->{ipver};
        }
        my $port = $p->{port} || '-';
        my $group = $proto_disp . '|' . $port;
        $by_port{$group} ||= {
            proto => $proto_disp,
            port  => $port,
            users => {},
            cmds  => {},
            pids  => {},
            local => {},
            rows  => 0,
        };
        my $g = $by_port{$group};
        $g->{rows}++;
        $g->{users}{$p->{user} || '-'} = 1;
        $g->{cmds}{$p->{command} || '-'} = 1;
        $g->{pids}{$p->{pid} || '-'} = 1;
        $g->{local}{$p->{local} || '-'} = 1;
    }

    my @port_cards;
    for my $k (sort {
            my ($ap,$apo) = split(/\|/, $a, 2);
            my ($bp,$bpo) = split(/\|/, $b, 2);
            ($ap cmp $bp) || (($apo =~ /^\d+$/ ? $apo : 999999) <=> ($bpo =~ /^\d+$/ ? $bpo : 999999)) || ($apo cmp $bpo)
        } keys %by_port) {
        my $g = $by_port{$k};
        my @users = sort keys %{ $g->{users} };
        my @cmds = sort { lc($a) cmp lc($b) } keys %{ $g->{cmds} };
        my @pids = sort { $a <=> $b } grep { /^\d+$/ } keys %{ $g->{pids} };
        my @locals = sort keys %{ $g->{local} };
        my $extra_local = 0;
        if (@locals > 6) {
            $extra_local = @locals - 6;
            @locals = @locals[0..5];
        }

        my $title = "<b>" . &html_escape($g->{proto}) . " : " . &html_escape($g->{port}) . "</b>";
        my $users_txt = @users ? join(', ', @users) : '-';
        my $cmds_txt = @cmds ? join(', ', @cmds) : '-';
        my $pids_txt = @pids ? join(', ', @pids) : '-';
        my $locals_txt = @locals ? join('<br>', map { &html_escape($_) } @locals) : '-';
        $locals_txt .= "<br>... (+$extra_local more)" if $extra_local > 0;
        my $body =
            "Listeners: " . int($g->{rows}) . "<br>" .
            "Commands: " . &html_escape($cmds_txt) . "<br>" .
            "Users: " . &html_escape($users_txt) . "<br>" .
            "PIDs: " . &html_escape($pids_txt) . "<br>" .
            "Local endpoints:<br>" . $locals_txt;
        push @port_cards, $title . "<br>" . $body;
    }

    print &ui_subheading("Listening Ports (grouped mosaic)");
    if (@port_cards) {
        $render_mosaic->(\@port_cards, 4);
    } else {
        print &ui_alert("No TCP/UDP listeners parsed.", "info");
    }
    if ($other_count > 0) {
        print &ui_alert("Non-network sockets (UNIX/local) are excluded from the grouped port mosaic: $other_count", "info");
    }
}

sub action_firewall {
    my $default_conf = '/etc/pf.conf';
    my $config_file = $in{'config_file'} || $default_conf;
    $config_file =~ s/^\s+|\s+$//g;
    if ($config_file !~ m{^/[A-Za-z0-9._/\-]+$}) {
        print &ui_print_error(L("ERR_PF_CONFIG_PATH_INVALID", $config_file));
        $config_file = $default_conf;
    }

    my $pfctl = $zfsguru_lib::PFCTL || '/sbin/pfctl';
    my $backup_dir = '/var/tmp/zfsguru-pf-backups';
    if (!-d $backup_dir) {
        mkdir $backup_dir;
    }

    if ($in{'save_pf_conf'}) {
        eval {
            die L("ERR_CONFIRM_REQUIRED") unless $in{'confirm_pf_save'};
            my $raw = defined $in{'pf_raw'} ? $in{'pf_raw'} : '';
            my $backup = write_file_with_backup($config_file, $raw);
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));

            if ($in{'test_pf_after_save'}) {
                my ($ok_test, $tout, $terr) = firewall_pf_test($config_file);
                die ($terr || $tout || "pf test failed") unless $ok_test;
                print &ui_print_success(L("SUCCESS_PF_TEST_OK", $config_file));
            }
            if ($in{'apply_pf_after_save'}) {
                die L("ERR_PF_APPLY_CONFIRM_REQUIRED") unless $in{'confirm_pf_apply'};
                my ($ok_reload, $rout, $rerr) = firewall_pf_reload($config_file);
                die ($rerr || $rout || "pf reload failed") unless $ok_reload;
                print &ui_print_success(L("SUCCESS_PF_RELOADED", $config_file));
            }
        };
        if ($@) {
            print &ui_print_error(L("ERR_PF_CONFIG_SAVE_FAILED", $@));
        }
    }

    if ($in{'backup_pf'}) {
        eval {
            die "Config not readable: $config_file" unless -r $config_file;
            my $ts = strftime("%Y%m%d-%H%M%S", localtime());
            my $backup_file = "$backup_dir/pf.conf.$ts.bak";
            copy_text_file($config_file, $backup_file);
            print &ui_print_success(L("SUCCESS_PF_BACKUP_CREATED", $backup_file));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PF_BACKUP_FAILED", $@));
        }
    }

    if ($in{'apply_pf'}) {
        eval {
            die L("ERR_PF_APPLY_CONFIRM_REQUIRED") unless $in{'confirm_pf_apply'};
            my ($ok_test, $tout, $terr) = firewall_pf_test($config_file);
            die ($terr || $tout || "pf test failed") unless $ok_test;

            my ($ok_reload, $rout, $rerr) = firewall_pf_reload($config_file);
            die ($rerr || $rout || "pf reload failed") unless $ok_reload;

            print &ui_print_success(L("SUCCESS_PF_RELOADED", $config_file));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PF_RELOAD_FAILED", $@));
        }
    }

    if ($in{'rollback_pf'}) {
        eval {
            die L("ERR_PF_ROLLBACK_CONFIRM_REQUIRED") unless $in{'confirm_pf_rollback'};
            my $backup_file = $in{'backup_file'} || '';
            die "Invalid backup file" unless $backup_file =~ /^[A-Za-z0-9._:-]+$/;
            my $src = "$backup_dir/$backup_file";
            die "Backup file not readable: $src" unless -r $src;

            copy_text_file($src, $config_file);
            my ($ok_test, $tout, $terr) = firewall_pf_test($config_file);
            die ($terr || $tout || "pf test failed after rollback") unless $ok_test;
            my ($ok_reload, $rout, $rerr) = firewall_pf_reload($config_file);
            die ($rerr || $rout || "pf reload failed after rollback") unless $ok_reload;

            print &ui_print_success(L("SUCCESS_PF_ROLLBACK_DONE", $backup_file));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PF_ROLLBACK_FAILED", $@));
        }
    }

    if ($in{'pf_runtime'}) {
        eval {
            die L("ERR_PF_TOGGLE_CONFIRM_REQUIRED") unless $in{'confirm_pf_toggle'};
            my $rt = $in{'pf_runtime_action'} || 'enable';
            if ($rt eq 'enable') {
                my ($rc, $out, $err) = run_cmd($pfctl, '-e');
                die ($err || $out || "pf enable failed") if $rc != 0;
            } elsif ($rt eq 'disable') {
                my ($rc, $out, $err) = run_cmd($pfctl, '-d');
                die ($err || $out || "pf disable failed") if $rc != 0;
            } elsif ($rt eq 'reload') {
                my ($ok_test, $tout, $terr) = firewall_pf_test($config_file);
                die ($terr || $tout || "pf test failed") unless $ok_test;
                my ($ok_reload, $rout, $rerr) = firewall_pf_reload($config_file);
                die ($rerr || $rout || "pf reload failed") unless $ok_reload;
            } else {
                die L("ERR_UPDATE_ACTION_INVALID");
            }
            if ($in{'persist_pf_enable'}) {
                my $pf_enable = ($rt eq 'disable') ? 'NO' : 'YES';
                set_rc_conf_value($RC_CONF, 'pf_enable', $pf_enable);
            }
            print &ui_print_success(L("SUCCESS_PF_RUNTIME_UPDATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PF_RUNTIME_FAILED", $@));
        }
    }

    my $pf = firewall_pf_info();
    my $status_class = $pf->{enabled} ? 'zfsguru-status-ok' : 'zfsguru-status-bad';
    my $status_text = $pf->{enabled} ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    my @backups = list_pf_backups($backup_dir);
    my $pf_enable = rc_conf_value($RC_CONF, 'pf_enable') || '-';

    print &ui_subheading(L("SUB_NET_FIREWALL"));
    print &ui_table_start(L("TABLE_PF_STATUS"), "width=100%", 2);
    print &ui_table_row(L("ROW_PF_STATUS"), "<span class='$status_class'>$status_text</span>");
    print &ui_table_row(L("ROW_PF_STATUS_LINE"), &html_escape($pf->{status_line}));
    print &ui_table_row(L("ROW_PF_RULES"), $pf->{rules_count});
    print &ui_table_row(L("ROW_PF_RC_ENABLE"), &html_escape($pf_enable));
    print &ui_table_end();

    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "firewall");
    print &ui_table_start(L("TABLE_PF_ACTIONS"), "width=100%", 2);
    print &ui_table_row(L("ROW_PF_CONFIG_FILE"), &ui_textbox("config_file", $config_file, 60));
    if (@backups) {
        print &ui_table_row(
            L("ROW_PF_BACKUP_FILE"),
            &ui_select("backup_file", $backups[0], [ map { [ $_, $_ ] } @backups ])
        );
    } else {
        print &ui_table_row(L("ROW_PF_BACKUP_FILE"), L("VALUE_NONE"));
    }
    print &ui_table_row(
        L("ROW_CONFIRM"),
        &ui_checkbox("confirm_pf_apply", 1, L("LBL_CONFIRM_PF_APPLY"), 0)
    );
    print &ui_table_row(
        L("ROW_CONFIRM_PF_ROLLBACK"),
        &ui_checkbox("confirm_pf_rollback", 1, L("LBL_CONFIRM_PF_ROLLBACK"), 0)
    );
    print &ui_table_end();
    print &ui_form_end([
        [ "backup_pf", L("BTN_PF_CREATE_BACKUP") ],
        [ "apply_pf", L("BTN_TEST_AND_RELOAD_PF") ],
        [ "rollback_pf", L("BTN_PF_ROLLBACK") ],
    ]);

    print &ui_hr();
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "firewall");
    print &ui_hidden("pf_runtime", 1);
    print &ui_table_start(L("TABLE_PF_RUNTIME"), "width=100%", 2);
    print &ui_table_row(
        L("ROW_PF_RUNTIME_ACTION"),
        &ui_select("pf_runtime_action", "reload", [
            [ "enable", L("OPT_PF_ENABLE") ],
            [ "disable", L("OPT_PF_DISABLE") ],
            [ "reload", L("OPT_PF_RELOAD") ],
        ])
    );
    print &ui_table_row(
        L("ROW_PF_PERSIST"),
        &ui_checkbox("persist_pf_enable", 1, L("LBL_PF_PERSIST"), 1)
    );
    print &ui_table_row(
        L("ROW_CONFIRM"),
        &ui_checkbox("confirm_pf_toggle", 1, L("LBL_CONFIRM_PF_TOGGLE"), 0)
    );
    print &ui_table_end();
    print &ui_form_end([ [ "pf_runtime", L("BTN_PF_APPLY_RUNTIME") ] ]);

    if (-r $config_file) {
        my $content = read_file_text($config_file);
        print &ui_hr();
        print &ui_subheading(L("SUB_PF_CONFIG_PREVIEW"));
        print &ui_form_start("network.cgi", "post");
        print &ui_hidden("action", "firewall");
        print &ui_hidden("save_pf_conf", 1);
        print &ui_table_start(L("TABLE_PF_EDITOR"), "width=100%", 2);
        print &ui_table_row(L("ROW_PF_CONFIG_FILE"), &html_escape($config_file));
        print &ui_table_row(L("ROW_PF_RAW"), &ui_textarea("pf_raw", $content, 16, 100));
        print &ui_table_row(L("ROW_PF_TEST_AFTER_SAVE"),
            &ui_checkbox("test_pf_after_save", 1, L("LBL_PF_TEST_AFTER_SAVE"), 1));
        print &ui_table_row(L("ROW_PF_APPLY_AFTER_SAVE"),
            &ui_checkbox("apply_pf_after_save", 1, L("LBL_PF_APPLY_AFTER_SAVE"), 0));
        print &ui_table_row(L("ROW_CONFIRM"),
            &ui_checkbox("confirm_pf_save", 1, L("LBL_CONFIRM_PF_SAVE"), 0));
        print &ui_table_row(L("ROW_CONFIRM"),
            &ui_checkbox("confirm_pf_apply", 1, L("LBL_CONFIRM_PF_APPLY"), 0));
        print &ui_table_end();
        print &ui_form_end([ [ "save_pf_conf", L("BTN_SAVE_PF_CONFIG") ] ]);
    }
}

sub action_dnsmasq {
    print &ui_subheading(L("SUB_NET_DNSMASQ"));
    print "<p>" . L("MSG_DNSMASQ_NOTE") . "</p>";

    _handle_dnsmasq_save(action => 'dnsmasq');

    my $file_ok = (-r $DNSMASQ_CONF) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    my $svc_ok = '-';
    eval {
        my ($rc, $out, $err) = service_run('dnsmasq', 'onestatus');
        $svc_ok = ($rc == 0) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    };

    print &ui_table_start(L("TABLE_DNSMASQ_STATUS"), "width=100%", 2);
    print &ui_table_row(L("ROW_DNSMASQ_CONFIG"), &html_escape($DNSMASQ_CONF));
    print &ui_table_row(L("ROW_DNSMASQ_STATUS"), &html_escape($file_ok));
    print &ui_table_row(L("ROW_DNSMASQ_SERVICE_STATUS"), &html_escape($svc_ok));
    print &ui_table_end();

    print &ui_hr();
    _render_dnsmasq_editor(action => 'dnsmasq', subheading_key => 'SUB_DNSMASQ_CONFIG_EDIT');
}

sub action_dns {
    print &ui_subheading(L("SUB_NET_DNS"));

    if ($in{'save_dns'}) {
        my $raw = defined $in{'resolv_raw'} ? $in{'resolv_raw'} : '';
        eval {
            my $backup = write_file_with_backup($RESOLV_CONF, $raw);
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DNS_CONFIG_SAVE_FAILED", $@));
        }
    }

    my $content = read_file_text($RESOLV_CONF);
    my @nameservers;
    my $search = '';
    my $domain = '';
    my $options = '';

    for my $line (split /\n/, ($content || '')) {
        $line =~ s/^\s+|\s+$//g;
        next if $line =~ /^\s*#/;
        if ($line =~ /^nameserver\s+(\S+)/) {
            push @nameservers, $1;
        } elsif ($line =~ /^search\s+(.+)$/) {
            $search = $1;
        } elsif ($line =~ /^domain\s+(.+)$/) {
            $domain = $1;
        } elsif ($line =~ /^options\s+(.+)$/) {
            $options = $1;
        }
    }

    print &ui_table_start(L("TABLE_DNS_STATUS"), "width=100%", 2);
    print &ui_table_row(L("ROW_DNS_NAMESERVERS"),
        @nameservers ? join(", ", map { &html_escape($_) } @nameservers) : L("VALUE_NONE"));
    print &ui_table_row(L("ROW_DNS_SEARCH"), &html_escape($search || '-'));
    print &ui_table_row(L("ROW_DNS_DOMAIN"), &html_escape($domain || '-'));
    print &ui_table_row(L("ROW_DNS_OPTIONS"), &html_escape($options || '-'));
    print &ui_table_row(L("ROW_DNS_CONFIG_FILE"), &html_escape($RESOLV_CONF));
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_DNS_CONFIG_EDIT"));
    print "<p>" . L("MSG_DNS_EDIT_NOTE") . "</p>";
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "dns");
    print &ui_hidden("save_dns", 1);
    print &ui_table_start(L("TABLE_DNS_EDIT"), "width=100%", 2);
    print &ui_table_row(L("ROW_DNS_CONFIG_FILE"), &html_escape($RESOLV_CONF));
    print &ui_table_row(L("ROW_DNS_RAW"),
        &ui_textarea("resolv_raw", $content, 12, 100));
    print &ui_table_end();
    print &ui_form_end([ [ "save_dns", L("BTN_SAVE_DNS_CONFIG") ] ]);
}

sub action_dhcp {
    print &ui_subheading(L("SUB_NET_DHCP"));
    print "<p>" . L("MSG_DHCP_NOTE") . "</p>";

    if ($in{'save_dhcp_server'}) {
        eval {
            my $enable = $in{'dhcpd_enable'} ? 'YES' : 'NO';
            my $ifaces = $in{'dhcpd_ifaces'} || '';
            my $flags  = $in{'dhcpd_flags'} || '';

            set_rc_conf_value($RC_CONF, 'dhcpd_enable', $enable);
            set_rc_conf_value($RC_CONF, 'dhcpd_ifaces', $ifaces) if length $ifaces;
            set_rc_conf_value($RC_CONF, 'dhcpd_flags',  $flags) if length $flags;

            if ($in{'restart_after_save'}) {
                service_run('dhcpd', 'restart');
            }
            print &ui_print_success(L("SUCCESS_DHCP_SERVER_SAVED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DHCP_SAVE_FAILED", $@));
        }
    }

    if ($in{'save_dhcpd_conf'}) {
        eval {
            my $raw = defined $in{'dhcpd_conf_raw'} ? $in{'dhcpd_conf_raw'} : '';
            my $backup = write_file_with_backup($DHCPD_CONF, $raw);
            if ($in{'restart_after_save'}) {
                service_run('dhcpd', 'restart');
            }
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DHCPD_CONF_SAVE_FAILED", $@));
        }
    }

    if ($in{'save_dhcp_clients'}) {
        eval {
            my $mode = $in{'dhcp_client_mode'} || 'append';
            my $require_confirm = ($mode eq 'overwrite') ? 1 : 0;
            my $confirmed = $in{'confirm_overwrite'} ? 1 : 0;

            my $ifs = normalized_network_interfaces_list();
            my $raw = read_file_text($RC_CONF);
            my $needs_confirm = 0;

            for my $if (@$ifs) {
                my $name = $if->{name};
                next unless $name =~ /^[A-Za-z0-9:_\-\.]+$/;
                next unless $in{"dhcp_client_$name"};
                my $key = "ifconfig_$name";
                my $cur = rc_conf_value_from_text($raw, $key) || '';

                if ($mode eq 'overwrite') {
                    if (length $cur && $cur !~ /(^|\s)DHCP(\s|$)/i) {
                        $needs_confirm = 1;
                    }
                    $raw = update_rc_conf_line($raw, $key, "DHCP");
                } else {
                    my $new = $cur;
                    if (!length $new) {
                        $new = "DHCP";
                    } elsif ($new !~ /(^|\s)DHCP(\s|$)/i) {
                        $new = $new . " DHCP";
                    }
                    $raw = update_rc_conf_line($raw, $key, $new);
                }
            }

            if ($require_confirm && $needs_confirm && !$confirmed) {
                die L("ERR_CONFIRM_OVERWRITE_REQUIRED");
            }

            my $backup = write_file_with_backup($RC_CONF, $raw);
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
            print &ui_print_success(L("SUCCESS_DHCP_CLIENTS_SAVED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_DHCP_CLIENT_SAVE_FAILED", $@));
        }
    }

    my $dhcpd_enable = rc_conf_value($RC_CONF, 'dhcpd_enable') || '-';
    my $dhcpd_ifaces = rc_conf_value($RC_CONF, 'dhcpd_ifaces') || '';
    my $dhcpd_flags = rc_conf_value($RC_CONF, 'dhcpd_flags') || '';

    my @dhcp_clients = rc_conf_dhcp_clients($RC_CONF);

    print &ui_table_start(L("TABLE_DHCP_STATUS"), "width=100%", 2);
    print &ui_table_row(L("ROW_DHCPD_ENABLE"), &html_escape($dhcpd_enable));
    print &ui_table_row(L("ROW_DHCPD_IFACES"), &html_escape($dhcpd_ifaces));
    print &ui_table_row(L("ROW_DHCPD_FLAGS"), &html_escape($dhcpd_flags));
    print &ui_table_row(L("ROW_DHCP_CLIENTS"),
        @dhcp_clients ? join(", ", map { &html_escape($_) } @dhcp_clients) : L("VALUE_NONE"));
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_DHCP_SERVER_EDIT"));
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "dhcp");
    print &ui_hidden("save_dhcp_server", 1);
    print &ui_table_start(L("TABLE_DHCP_SERVER_EDIT"), "width=100%", 2);
    print &ui_table_row(L("ROW_DHCPD_ENABLE"),
        &ui_checkbox("dhcpd_enable", 1, L("OPT_ENABLED"),
            ($dhcpd_enable =~ /^(yes|on|true|1)$/i) ? 1 : 0));
    print &ui_table_row(L("ROW_DHCPD_IFACES"), &ui_textbox("dhcpd_ifaces", $dhcpd_ifaces, 40));
    print &ui_table_row(L("ROW_DHCPD_FLAGS"), &ui_textbox("dhcpd_flags", $dhcpd_flags, 40));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "save_dhcp_server", L("BTN_SAVE_DHCP_SERVER") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_DHCP_CLIENT_EDIT"));
    print "<p>" . L("MSG_DHCP_CLIENT_NOTE") . "</p>";
    my $ifs = normalized_network_interfaces_list();
    my $dhcp_client_mode = $in{'dhcp_client_mode'} || 'append';
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "dhcp");
    print &ui_hidden("save_dhcp_clients", 1);
    print &ui_table_start(L("TABLE_DHCP_CLIENT_EDIT"), "width=100%", 2);
    print &ui_table_row(L("ROW_DHCP_CLIENT_MODE"), &ui_select("dhcp_client_mode", $dhcp_client_mode, [
        [ "append", L("OPT_APPEND_DHCP") ],
        [ "overwrite", L("OPT_OVERWRITE_DHCP") ],
    ]));
    print &ui_table_row(L("ROW_CONFIRM_OVERWRITE"), &ui_checkbox("confirm_overwrite", 1, L("LBL_CONFIRM_OVERWRITE"), 0));
    my $warn_class = ($dhcp_client_mode eq 'overwrite') ? "" : "zfsguru-hidden";
    print &ui_table_row(
        "",
        "<div id='dhcp-overwrite-warning' class='$warn_class'>" .
        &ui_print_error(L("MSG_DHCP_OVERWRITE_WARNING")) .
        "</div>"
    );
    for my $if (@$ifs) {
        my $name = $if->{name};
        next unless $name =~ /^[A-Za-z0-9:_\-\.]+$/;
        my $checked = (grep { $_ eq $name } @dhcp_clients) ? 1 : 0;
        print &ui_table_row($name, &ui_checkbox("dhcp_client_$name", 1, L("OPT_ENABLED"), $checked));
    }
    print &ui_table_end();
    print &ui_form_end([ [ "save_dhcp_clients", L("BTN_SAVE_DHCP_CLIENTS") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_DHCPD_CONFIG_EDIT"));
    my $dhcpd_raw = read_file_text($DHCPD_CONF);
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "dhcp");
    print &ui_hidden("save_dhcpd_conf", 1);
    print &ui_table_start(L("TABLE_DHCPD_CONFIG_EDIT"), "width=100%", 2);
    print &ui_table_row(L("ROW_DHCPD_CONFIG_FILE"), &html_escape($DHCPD_CONF));
    print &ui_table_row(L("ROW_DHCPD_RAW"),
        &ui_textarea("dhcpd_conf_raw", $dhcpd_raw, 12, 100));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "save_dhcpd_conf", L("BTN_SAVE_DHCPD_CONFIG") ] ]);

    my @leases = dhclient_lease_files();
    print &ui_subheading(L("SUB_DHCP_LEASES"));
    print &ui_table_start(L("TABLE_DHCP_LEASES"), "width=100%", 2, [
        L("COL_FILE"), L("COL_SIZE"), L("COL_MODIFIED")
    ]);
    if (@leases) {
        for my $lf (@leases) {
            print &ui_table_row(
                &html_escape($lf->{file}),
                &html_escape($lf->{size}),
                &html_escape($lf->{mtime})
            );
        }
    } else {
        print &ui_table_row("-", "-", "-");
    }
    print &ui_table_end();
}

sub action_lagg {
    print &ui_subheading(L("SUB_NET_LAGG"));

    if ($in{'save_lagg'}) {
        eval {
            my $lagg_name = $in{'lagg_name'} || 'lagg0';
            my $proto = $in{'lagg_proto'} || 'lacp';
            my $ports = $in{'lagg_ports'} || '';
            my $extra = $in{'lagg_extra'} || '';

            die "Invalid lagg name" unless $lagg_name =~ /^lagg\d+$/;
            die "Missing ports" unless $ports =~ /\S/;

            my @port_list = grep { length } split(/\s+/, $ports);
            for my $p (@port_list) {
                die "Invalid port $p" unless $p =~ /^[A-Za-z0-9:_\-\.]+$/;
            }

            my $ifconfig = "laggproto $proto";
            for my $p (@port_list) {
                $ifconfig .= " laggport $p";
            }
            $ifconfig .= " $extra" if length $extra;

            add_to_rc_conf_list($RC_CONF, 'cloned_interfaces', $lagg_name);
            set_rc_conf_value($RC_CONF, "ifconfig_$lagg_name", $ifconfig);

            if ($in{'apply_now'}) {
                my $ifc = '/sbin/ifconfig';
                {
                    no warnings 'once';
                    $ifc = $zfsguru_lib::IFCONFIG if $zfsguru_lib::IFCONFIG;
                }
                run_cmd($ifc, $lagg_name, 'create');
                run_cmd($ifc, $lagg_name, split(/\s+/, $ifconfig));
            }
            print &ui_print_success(L("SUCCESS_LAGG_SAVED", $lagg_name));
        };
        if ($@) {
            print &ui_print_error(L("ERR_LAGG_SAVE_FAILED", $@));
        }
    }

    my $ifconfig = '/sbin/ifconfig';
    {
        no warnings 'once';
        $ifconfig = $zfsguru_lib::IFCONFIG if $zfsguru_lib::IFCONFIG;
    }
    my ($rc, $out, $err) = run_cmd($ifconfig, '-a');
    if ($rc != 0 || !$out) {
        print &ui_print_error(L("ERR_LAGG_LIST_FAILED", $err || 'ifconfig failed'));
        return;
    }

    my $laggs = parse_lagg_interfaces($out);
    print &ui_table_start(L("TABLE_LAGG"), "width=100%", 2, [
        L("COL_INTERFACE"), L("COL_LAGG_PROTO"), L("COL_LAGG_PORTS"),
        L("COL_STATUS"), L("COL_FLAGS")
    ]);
    if (@$laggs) {
        for my $lg (@$laggs) {
            print &ui_table_row(
                &html_escape($lg->{name}),
                &html_escape($lg->{proto} || '-'),
                &html_escape(@{ $lg->{ports} } ? join(', ', @{ $lg->{ports} }) : '-'),
                &html_escape($lg->{status} || '-'),
                &html_escape($lg->{flags} || '-')
            );
        }
    } else {
        print &ui_table_row("-", "-", "-", "-", "-");
    }
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_LAGG_CONFIG_EDIT"));
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "lagg");
    print &ui_hidden("save_lagg", 1);
    print &ui_table_start(L("TABLE_LAGG_EDIT"), "width=100%", 2);
    print &ui_table_row(L("ROW_LAGG_NAME"), &ui_textbox("lagg_name", "lagg0", 10));
    print &ui_table_row(L("ROW_LAGG_PROTO"), &ui_select("lagg_proto", "lacp", [
        [ "lacp", "lacp" ],
        [ "failover", "failover" ],
        [ "loadbalance", "loadbalance" ],
        [ "roundrobin", "roundrobin" ],
    ]));
    print &ui_table_row(L("ROW_LAGG_PORTS"), &ui_textbox("lagg_ports", "", 40));
    print &ui_table_row(L("ROW_LAGG_EXTRA"), &ui_textbox("lagg_extra", "up", 20));
    print &ui_table_row(L("ROW_APPLY_NOW"), &ui_checkbox("apply_now", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "save_lagg", L("BTN_SAVE_LAGG") ] ]);
}

sub action_pxe {
    print &ui_subheading(L("SUB_NET_PXE"));
    print "<p>" . L("MSG_PXE_NOTE") . "</p>";

    _handle_dnsmasq_save(action => 'pxe');

    if ($in{'save_pxe_profile'}) {
        eval {
            my $iface = $in{'pxe_iface'} || '';
            my $range_start = $in{'pxe_range_start'} || '';
            my $range_end = $in{'pxe_range_end'} || '';
            my $range_mask = $in{'pxe_range_mask'} || '255.255.255.0';
            my $boot_file = $in{'pxe_boot_file'} || '';
            my $next_server = $in{'pxe_next_server'} || '';
            my $tftp_root = $in{'pxe_tftp_root'} || $TFTPBOOT_DIR;

            die L("ERR_PXE_INVALID_INTERFACE", $iface)
                if length($iface) && $iface !~ /^[A-Za-z0-9:_\-\.]+$/;
            die L("ERR_PXE_INVALID_IPV4", $range_start) if length($range_start) && !valid_ipv4($range_start);
            die L("ERR_PXE_INVALID_IPV4", $range_end) if length($range_end) && !valid_ipv4($range_end);
            die L("ERR_PXE_INVALID_IPV4", $range_mask) if !valid_ipv4($range_mask);
            die L("ERR_PXE_INVALID_PATH", $boot_file) if !length($boot_file) || $boot_file =~ m{^\s*/} || $boot_file =~ m{\.\.};
            die L("ERR_PXE_INVALID_IPV4", $next_server) if length($next_server) && !valid_ipv4($next_server);
            die L("ERR_PXE_INVALID_PATH", $tftp_root) if $tftp_root !~ m{^/};

            my @lines;
            push @lines, "interface=$iface" if length $iface;
            push @lines, "bind-interfaces" if length $iface;
            if (length($range_start) && length($range_end)) {
                push @lines, "dhcp-range=$range_start,$range_end,$range_mask,12h";
            }
            push @lines, "enable-tftp";
            push @lines, "tftp-root=$tftp_root";
            push @lines, length($next_server)
                ? "dhcp-boot=$boot_file,$next_server"
                : "dhcp-boot=$boot_file";

            my $raw = read_file_text($DNSMASQ_CONF);
            my $new_raw = dnsmasq_replace_managed_block($raw, \@lines);
            my $backup = write_file_with_backup($DNSMASQ_CONF, $new_raw);
            if ($in{'restart_after_save'}) {
                service_run('dnsmasq', 'restart');
            }
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
            print &ui_print_success(L("SUCCESS_PXE_PROFILE_SAVED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PXE_PROFILE_SAVE_FAILED", $@));
        }
    }

    if ($in{'create_tftp_root'}) {
        eval {
            ensure_dir($TFTPBOOT_DIR, 0755);
            print &ui_print_success(L("SUCCESS_TFTP_ROOT_CREATED", $TFTPBOOT_DIR));
        };
        if ($@) {
            print &ui_print_error(L("ERR_TFTP_ROOT_CREATE_FAILED", $@));
        }
    }

    if ($in{'toggle_tftp'}) {
        eval {
            my $enable = $in{'tftp_enable'} ? 1 : 0;
            my $raw = read_file_text($INETD_CONF);
            my $new_raw = update_inetd_tftp($raw, $enable, $TFTPBOOT_DIR);
            my $backup = write_file_with_backup($INETD_CONF, $new_raw);
            if ($in{'restart_after_save'}) {
                service_run('inetd', 'restart');
            }
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
        };
        if ($@) {
            print &ui_print_error(L("ERR_INETD_SAVE_FAILED", $@));
        }
    }

    if ($in{'pxe_service_action'}) {
        eval {
            my $svc = $in{'pxe_service'} || '';
            my $act = $in{'pxe_service_action_name'} || '';
            die L("ERR_PXE_SERVICE_INVALID", $svc)
                unless $svc =~ /^(dnsmasq|inetd)$/;
            die L("ERR_UPDATE_ACTION_INVALID")
                unless $act =~ /^(start|stop|restart|reload)$/;
            my ($rc, $out, $err) = service_run($svc, $act);
            die ($err || $out || "service action failed") if $rc != 0;
            print &ui_print_success(L("SUCCESS_PXE_SERVICE_ACTION", $svc, $act));
        };
        if ($@) {
            print &ui_print_error(L("ERR_PXE_SERVICE_ACTION_FAILED", $@));
        }
    }

    my $tftp_ok = (-d $TFTPBOOT_DIR) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    my $dnsmasq_ok = (-r $DNSMASQ_CONF) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    my $inetd_ok = '-';
    my $dnsmasq_svc = '-';
    my $inetd_svc = '-';
    eval {
        my ($rc, $out, $err) = service_run('dnsmasq', 'onestatus');
        $dnsmasq_svc = ($rc == 0) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    };
    eval {
        my ($rc, $out, $err) = service_run('inetd', 'onestatus');
        $inetd_svc = ($rc == 0) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    };
    if (-r $INETD_CONF) {
        my $inetd_txt = read_file_text($INETD_CONF);
        $inetd_ok = ($inetd_txt =~ /^\s*tftp\s+/m) ? L("VALUE_ENABLED") : L("VALUE_DISABLED");
    }

    print &ui_table_start(L("TABLE_PXE"), "width=100%", 2);
    print &ui_table_row(L("ROW_TFTPBOOT_DIR"), &html_escape($TFTPBOOT_DIR));
    print &ui_table_row(L("ROW_TFTPBOOT_STATUS"), &html_escape($tftp_ok));
    print &ui_table_row(L("ROW_DNSMASQ_CONFIG"), &html_escape($DNSMASQ_CONF));
    print &ui_table_row(L("ROW_DNSMASQ_STATUS"), &html_escape($dnsmasq_ok));
    print &ui_table_row(L("ROW_DNSMASQ_SERVICE_STATUS"), &html_escape($dnsmasq_svc));
    print &ui_table_row(L("ROW_INETD_TFTP"), &html_escape($inetd_ok));
    print &ui_table_row(L("ROW_INETD_SERVICE_STATUS"), &html_escape($inetd_svc));
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_PXE_TFTP"));
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "pxe");
    print &ui_hidden("toggle_tftp", 1);
    print &ui_table_start(L("TABLE_TFTP_SETTINGS"), "width=100%", 2);
    print &ui_table_row(L("ROW_TFTPBOOT_DIR"), &html_escape($TFTPBOOT_DIR));
    print &ui_table_row(L("ROW_TFTP_ENABLE"), &ui_checkbox("tftp_enable", 1, L("OPT_ENABLED"), ($inetd_ok eq L("VALUE_ENABLED")) ? 1 : 0));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "toggle_tftp", L("BTN_SAVE_TFTP") ], [ "create_tftp_root", L("BTN_CREATE_TFTP_ROOT") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_PXE_SERVICES"));
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "pxe");
    print &ui_hidden("pxe_service_action", 1);
    print &ui_table_start(L("TABLE_PXE_SERVICES"), "width=100%", 2);
    print &ui_table_row(
        L("ROW_PXE_SERVICE"),
        &ui_select("pxe_service", "dnsmasq", [
            [ "dnsmasq", "dnsmasq" ],
            [ "inetd", "inetd" ],
        ])
    );
    print &ui_table_row(
        L("ROW_PXE_SERVICE_ACTION"),
        &ui_select("pxe_service_action_name", "restart", [
            [ "start", L("BTN_START") ],
            [ "stop", L("BTN_STOP") ],
            [ "restart", L("BTN_RESTART") ],
            [ "reload", "reload" ],
        ])
    );
    print &ui_table_end();
    print &ui_form_end([ [ "pxe_service_action", L("BTN_APPLY") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_PXE_PROFILE"));
    print "<p>" . L("MSG_PXE_PROFILE_NOTE") . "</p>";
    my $dnsmasq_raw = read_file_text($DNSMASQ_CONF);
    my $profile = pxe_profile_from_dnsmasq($dnsmasq_raw);
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", "pxe");
    print &ui_hidden("save_pxe_profile", 1);
    print &ui_table_start(L("TABLE_PXE_PROFILE"), "width=100%", 2);
    print &ui_table_row(L("ROW_PXE_INTERFACE"), &ui_textbox("pxe_iface", ($profile->{iface} || ''), 20));
    print &ui_table_row(L("ROW_PXE_RANGE_START"), &ui_textbox("pxe_range_start", ($profile->{range_start} || ''), 20));
    print &ui_table_row(L("ROW_PXE_RANGE_END"), &ui_textbox("pxe_range_end", ($profile->{range_end} || ''), 20));
    print &ui_table_row(L("ROW_PXE_RANGE_MASK"), &ui_textbox("pxe_range_mask", ($profile->{range_mask} || '255.255.255.0'), 20));
    print &ui_table_row(L("ROW_PXE_BOOT_FILE"), &ui_textbox("pxe_boot_file", ($profile->{boot_file} || 'pxeboot'), 30));
    print &ui_table_row(L("ROW_PXE_NEXT_SERVER"), &ui_textbox("pxe_next_server", ($profile->{next_server} || ''), 20));
    print &ui_table_row(L("ROW_TFTPBOOT_DIR"), &ui_textbox("pxe_tftp_root", ($profile->{tftp_root} || $TFTPBOOT_DIR), 40));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 1));
    print &ui_table_end();
    print &ui_form_end([ [ "save_pxe_profile", L("BTN_SAVE_PXE_PROFILE") ] ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_PXE_TFTP_FILES"));
    my $entries = tftp_root_entries($TFTPBOOT_DIR, 200);
    my @heads = (L("COL_FILE"), L("COL_SIZE"), L("COL_MODIFIED"));
    my @data;
    for my $e (@$entries) {
        push @data, [
            &html_escape($e->{path} || ''),
            &html_escape($e->{size} || '-'),
            &html_escape($e->{mtime} || '-'),
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_PXE_TFTP_FILES"), L("VALUE_NONE"));

    print &ui_hr();
    _render_dnsmasq_editor(action => 'pxe', subheading_key => 'SUB_PXE_DNSMASQ_EDIT');
}

sub _handle_dnsmasq_save {
    my (%opt) = @_;

    return unless $in{'save_dnsmasq'};

    eval {
        my $raw = defined $in{'dnsmasq_raw'} ? $in{'dnsmasq_raw'} : '';
        my $backup = write_file_with_backup($DNSMASQ_CONF, $raw);
        if ($in{'restart_after_save'}) {
            service_run('dnsmasq', 'restart');
        }
        print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
    };
    if ($@) {
        print &ui_print_error(L("ERR_DNSMASQ_SAVE_FAILED", $@));
    }
}

sub _render_dnsmasq_editor {
    my (%opt) = @_;
    my $action = $opt{action} || 'dnsmasq';
    my $subheading_key = $opt{subheading_key} || 'SUB_DNSMASQ_CONFIG_EDIT';

    print &ui_subheading(L($subheading_key));

    my $dnsmasq_raw = read_file_text($DNSMASQ_CONF);
    print &ui_form_start("network.cgi", "post");
    print &ui_hidden("action", $action);
    print &ui_hidden("save_dnsmasq", 1);
    print &ui_table_start(L("TABLE_DNSMASQ_EDIT"), "width=100%", 2);
    print &ui_table_row(L("ROW_DNSMASQ_CONFIG"), &html_escape($DNSMASQ_CONF));
    print &ui_table_row(L("ROW_DNSMASQ_RAW"),
        &ui_textarea("dnsmasq_raw", $dnsmasq_raw, 12, 100));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "save_dnsmasq", L("BTN_SAVE_DNSMASQ") ] ]);
}

sub valid_ipv4 {
    my ($ip) = @_;
    return 0 unless defined $ip && $ip =~ /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/;
    for my $o ($1, $2, $3, $4) {
        return 0 if $o < 0 || $o > 255;
    }
    return 1;
}

sub dnsmasq_replace_managed_block {
    my ($raw, $lines) = @_;
    $raw = '' unless defined $raw;
    $lines = [] unless ref($lines) eq 'ARRAY';
    my $begin = '# BEGIN ZFSGURU_PXE';
    my $end   = '# END ZFSGURU_PXE';

    my @out;
    my $skip = 0;
    for my $line (split /\n/, $raw, -1) {
        if ($line =~ /^\Q$begin\E\s*$/) {
            $skip = 1;
            next;
        }
        if ($skip && $line =~ /^\Q$end\E\s*$/) {
            $skip = 0;
            next;
        }
        next if $skip;
        push @out, $line;
    }

    my $new_raw = join("\n", @out);
    $new_raw .= "\n" if length($new_raw) && $new_raw !~ /\n\z/;
    $new_raw .= "\n" if length($new_raw);
    $new_raw .= "$begin\n";
    for my $l (@$lines) {
        next unless defined $l && length $l;
        $new_raw .= "$l\n";
    }
    $new_raw .= "$end\n";
    return $new_raw;
}

sub pxe_profile_from_dnsmasq {
    my ($raw) = @_;
    my %p = (
        iface       => '',
        range_start => '',
        range_end   => '',
        range_mask  => '255.255.255.0',
        boot_file   => '',
        next_server => '',
        tftp_root   => '',
    );
    return \%p unless defined $raw && length $raw;

    my $begin = '# BEGIN ZFSGURU_PXE';
    my $end   = '# END ZFSGURU_PXE';
    my $in = 0;
    for my $line (split /\n/, $raw) {
        if ($line =~ /^\Q$begin\E\s*$/) {
            $in = 1;
            next;
        }
        if ($in && $line =~ /^\Q$end\E\s*$/) {
            last;
        }
        next unless $in;
        $line =~ s/^\s+|\s+$//g;
        next if $line eq '' || $line =~ /^\s*#/;

        if ($line =~ /^interface=(.+)$/) {
            $p{iface} = $1;
        } elsif ($line =~ /^dhcp-range=([^,]+),([^,]+),([^,]+),?.*$/) {
            $p{range_start} = $1;
            $p{range_end} = $2;
            $p{range_mask} = $3;
        } elsif ($line =~ /^tftp-root=(.+)$/) {
            $p{tftp_root} = $1;
        } elsif ($line =~ /^dhcp-boot=([^,]+)(?:,([^,]+))?.*$/) {
            $p{boot_file} = $1;
            $p{next_server} = $2 || '';
        }
    }

    return \%p;
}

sub tftp_root_entries {
    my ($root, $limit) = @_;
    $root ||= '/tftpboot';
    $limit ||= 200;
    return [] unless -d $root;

    my @rows;
    my @stack = ($root);
    while (@stack && @rows < $limit) {
        my $dir = shift @stack;
        opendir(my $dh, $dir) or next;
        my @ents = grep { $_ ne '.' && $_ ne '..' } readdir($dh);
        closedir($dh);
        for my $e (sort @ents) {
            my $p = "$dir/$e";
            my $rel = $p;
            $rel =~ s/^\Q$root\E\/?//;
            if (-d $p) {
                push @rows, { path => $rel . '/', size => '-', mtime => '-' };
                push @stack, $p if @stack < 500;
            } elsif (-f $p) {
                my @st = stat($p);
                push @rows, {
                    path => $rel,
                    size => ($st[7] // 0),
                    mtime => ($st[9] ? scalar localtime($st[9]) : '-'),
                };
            }
            last if @rows >= $limit;
        }
    }
    return \@rows;
}

sub list_pf_backups {
    my ($dir) = @_;
    return () unless defined $dir && -d $dir;
    opendir(my $dh, $dir) or return ();
    my @all = grep { /^pf\.conf\.\d{8}-\d{6}\.bak$/ } readdir($dh);
    closedir($dh);
    @all = sort { $b cmp $a } @all;
    return @all;
}

sub rc_conf_value_from_text {
    my ($raw, $key) = @_;
    return undef unless defined $raw && defined $key;
    for my $line (split /\n/, $raw) {
        next if $line =~ /^\s*#/;
        next unless $line =~ /^\s*\Q$key\E\s*=\s*(.+?)\s*$/;
        my $value = $1;
        $value =~ s/^"(.*)"$/$1/;
        $value =~ s/^'(.*)'$/$1/;
        return $value;
    }
    return undef;
}

sub update_rc_conf_line {
    my ($raw, $key, $value) = @_;
    $raw = '' unless defined $raw;
    my $line = $key . '="' . $value . '"';
    if ($raw =~ /^\s*\Q$key\E\s*=\s*.*$/m) {
        $raw =~ s/^\s*\Q$key\E\s*=\s*.*$/$line/m;
    } else {
        $raw .= "\n" if length($raw) && $raw !~ /\n\z/;
        $raw .= $line . "\n";
    }
    return $raw;
}

sub rc_conf_dhcp_clients {
    my ($path) = @_;
    my $raw = read_file_text($path);
    return () unless length $raw;
    my @ifs;
    for my $line (split /\n/, $raw) {
        next if $line =~ /^\s*#/;
        if ($line =~ /^\s*ifconfig_(\S+)\s*=\s*\"([^\"]+)\"/) {
            my ($iface, $val) = ($1, $2);
            push @ifs, $iface if $val =~ /\bDHCP\b/i;
        }
    }
    return @ifs;
}

sub add_to_rc_conf_list {
    my ($path, $key, $item) = @_;
    my $cur = rc_conf_value($path, $key) || '';
    my @vals = grep { length } split(/\s+/, $cur);
    my %seen = map { $_ => 1 } @vals;
    if (!$seen{$item}) {
        push @vals, $item;
    }
    return set_rc_conf_value($path, $key, join(' ', @vals));
}

sub dhclient_lease_files {
    my @files;
    my $dir = '/var/db';
    return () unless -d $dir;
    opendir(my $dh, $dir) or return ();
    my @all = grep { /^dhclient\.leases\./ } readdir($dh);
    closedir($dh);
    for my $f (@all) {
        my $path = "$dir/$f";
        my @st = stat($path);
        next unless @st;
        push @files, {
            file => $path,
            size => $st[7],
            mtime => scalar localtime($st[9]),
        };
    }
    return @files;
}

sub normalized_network_interfaces_list {
    my $raw = network_interfaces_list();
    return [] unless ref($raw) eq 'ARRAY' && @$raw;

    my @out;
    for my $item (@$raw) {
        if (ref($item) eq 'HASH') {
            my $name = $item->{name} || '';
            next unless $name =~ /^[A-Za-z0-9:_\-.]+$/;
            push @out, {
                name      => $name,
                ipv4_text => ($item->{ipv4_text} // '-'),
                ipv6_text => ($item->{ipv6_text} // '-'),
                status    => ($item->{status} // '-'),
                mtu       => ($item->{mtu} // '-'),
                mac       => ($item->{mac} // '-'),
            };
            next;
        }

        next unless defined $item && $item =~ /^[A-Za-z0-9:_\-.]+$/;
        my $d = normalized_network_interface_details($item);
        push @out, {
            name      => $item,
            ipv4_text => format_inet4_summary($d->{inet}),
            ipv6_text => format_inet6_summary($d->{inet6}),
            status    => ($d->{status} || '-'),
            mtu       => ($d->{mtu} || '-'),
            mac       => ($d->{ether} || '-'),
        };
    }
    return \@out;
}

sub normalized_network_interface_details {
    my ($ifname) = @_;
    return {} unless defined $ifname && $ifname =~ /^[A-Za-z0-9:_\-.]+$/;
    my $raw = network_interface_details($ifname);
    if (ref($raw) eq 'HASH') {
        return $raw;
    }
    return parse_ifconfig_details_text($ifname, (defined $raw ? $raw : ''));
}

sub parse_ifconfig_details_text {
    my ($ifname, $raw) = @_;
    my %d = (
        ifname => $ifname,
        ident => '-',
        status => '-',
        linkspeed => '-',
        flags_str => '-',
        options_str => '-',
        ether => '-',
        mtu => '-',
        inet => [],
        inet6 => [],
    );

    for my $line (split /\n/, ($raw || '')) {
        if ($line =~ /^\Q$ifname\E:\s+flags=\d+<([^>]+)>.*\smtu\s+(\d+)/) {
            $d{flags_str} = $1 || '-';
            $d{mtu} = $2 || '-';
        }
        if ($line =~ /^\s*description:\s+(.+?)\s*$/) {
            $d{ident} = $1 if defined $1 && length $1;
        }
        if ($line =~ /^\s*status:\s+(.+?)\s*$/) {
            $d{status} = $1 if defined $1 && length $1;
        }
        if ($line =~ /^\s*media:\s+(.+?)\s*$/) {
            $d{linkspeed} = $1 if defined $1 && length $1;
        }
        if ($line =~ /^\s*options=\d+<([^>]+)>/) {
            $d{options_str} = $1 if defined $1 && length $1;
        }
        if ($line =~ /^\s*ether\s+([0-9a-f:]{17})/i) {
            $d{ether} = lc($1);
        }
        if ($line =~ /^\s*inet\s+(\S+)\s+netmask\s+(\S+)(?:\s+broadcast\s+(\S+))?/) {
            push @{ $d{inet} }, {
                ip => $1, netmask => $2, subnet => $2, broadcast => ($3 || '-'),
            };
        }
        if ($line =~ /^\s*inet6\s+(\S+)\s+prefixlen\s+(\d+)(?:\s+scopeid\s+(\S+))?/) {
            push @{ $d{inet6} }, {
                ip => $1, prefixlen => $2, scopeid => ($3 || '-'),
            };
        }
    }

    return \%d;
}

sub format_inet4_summary {
    my ($rows) = @_;
    return '-' unless ref($rows) eq 'ARRAY' && @$rows;
    my @ips = map { $_->{ip} || () } @$rows;
    return @ips ? join(', ', @ips) : '-';
}

sub format_inet6_summary {
    my ($rows) = @_;
    return '-' unless ref($rows) eq 'ARRAY' && @$rows;
    my @ips = map { $_->{ip} || () } @$rows;
    return @ips ? join(', ', @ips) : '-';
}

sub parse_lagg_interfaces {
    my ($out) = @_;
    my @laggs;
    my $cur;
    for my $line (split /\n/, ($out || '')) {
        if ($line =~ /^([A-Za-z0-9:_\-.]+):\s+flags=\d+<([^>]+)>/) {
            push @laggs, $cur if $cur && $cur->{is_lagg};
            $cur = {
                name => $1,
                flags => $2,
                proto => '',
                status => '',
                ports => [],
                is_lagg => ($1 =~ /^lagg\d+/) ? 1 : 0,
            };
            next;
        }
        next unless $cur && $cur->{is_lagg};
        if ($line =~ /^\s+laggproto\s+(\S+)/) {
            $cur->{proto} = $1;
        } elsif ($line =~ /^\s+laggport:\s+(\S+)/) {
            push @{ $cur->{ports} }, $1;
        } elsif ($line =~ /^\s+status:\s+(.+)$/) {
            $cur->{status} = $1;
        }
    }
    push @laggs, $cur if $cur && $cur->{is_lagg};
    return \@laggs;
}

sub update_inetd_tftp {
    my ($raw, $enable, $root) = @_;
    my @lines = split /\n/, ($raw || ''), -1;
    my $found = 0;
    for my $i (0 .. $#lines) {
        if ($lines[$i] =~ /^\s*#?\s*tftp\s+/) {
            $found = 1;
            if ($enable) {
                $lines[$i] =~ s/^\s*#\s*//;
            } else {
                $lines[$i] = '#' . $lines[$i] unless $lines[$i] =~ /^\s*#/;
            }
        }
    }
    if (!$found && $enable) {
        my $line = "tftp\tdgram\tudp\twait\troot\t/usr/libexec/tftpd\t" .
                   "tftpd -l -s " . ($root || '/tftpboot');
        push @lines, $line;
    }
    my $new_raw = join("\n", @lines);
    $new_raw .= "\n" if $new_raw !~ /\n\z/;
    return $new_raw;
}

1;
