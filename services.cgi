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

# Parse CGI params
zfsguru_readparse();
zfsguru_init('en');

my $RC_CONF      = '/etc/rc.conf';
my $EXPORTS_FILE = '/etc/exports';
my $SMB_CONF     = '/usr/local/etc/smb4.conf';
my $SSHD_CONF    = '/etc/ssh/sshd_config';
my $CTL_CONF     = '/etc/ctl.conf';
my $BACKUP_DIR   = '/var/tmp/zfsguru-config-backups';

zfsguru_page_header(title_key => "TITLE_SERVICES");

eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('services'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'services'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'manage';
my $service = $in{'service'} || '';

# Plain anchor tabs for reliable switching (works with &ReadParse)
my @tabs_list = (
    [ 'manage', 'TAB_SERVICES' ],
    [ 'nfs', 'TAB_NFS' ],
    [ 'smb', 'TAB_SMB' ],
    [ 'ssh', 'TAB_SSH' ],
    [ 'iscsi', 'TAB_ISCSI' ],
);

print zfsguru_print_tabs(
    script => 'services.cgi',
    active => $action,
    tabs   => \@tabs_list,
);

if ($action eq 'manage') {
    &action_manage();
} elsif ($action eq 'nfs') {
    &action_nfs();
} elsif ($action eq 'smb') {
    &action_smb();
} elsif ($action eq 'ssh') {
    &action_ssh();
} elsif ($action eq 'iscsi') {
    &action_iscsi();
} elsif ($action eq 'service_control') {
    &action_service_control();
}

my $back_url = 'index.cgi';
if ($action ne 'manage') {
    $back_url = 'services.cgi?action=manage';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_manage {
    print &ui_subheading(L("SUB_SYSTEM_SERVICES"));
    
    my @services = (
        { name => 'nfs', display => L('SVC_NFS'), cmd => 'nfsd' },
        { name => 'smb', display => L('SVC_SMB'), cmd => 'smbd' },
        { name => 'ssh', display => L('SVC_SSH'), cmd => 'sshd' },
        { name => 'iscsi', display => L('SVC_ISCSI'), cmd => 'ctld' },
    );
    
    print &ui_table_start(L("TABLE_SYSTEM_SERVICES"), "width=100%", 2, [
        L("COL_SERVICE"), L("COL_STATUS"), L("COL_ACTIONS")
    ]);
    
    for my $svc (@services) {
        my ($state) = service_state($svc->{cmd});
        my $status =
            $state eq 'running' ? "<span class='zfsguru-status-ok'>" . L("VALUE_RUNNING") . "</span>" :
            $state eq 'stopped' ? "<span class='zfsguru-status-bad'>" . L("VALUE_STOPPED") . "</span>" :
                                  "<span class='zfsguru-status-unknown'>" . L("VALUE_UNKNOWN") . "</span>";
        
        print &ui_table_row(
            $svc->{display},
            $status,
            "",
            [
                [ "services.cgi?action=service_control&service=$svc->{name}&cmd=start", L("BTN_START") ],
                [ "services.cgi?action=service_control&service=$svc->{name}&cmd=stop", L("BTN_STOP") ],
                [ "services.cgi?action=service_control&service=$svc->{name}&cmd=restart", L("BTN_RESTART") ],
                [ "services.cgi?action=$svc->{name}", L("BTN_CONFIGURE") ],
            ]
        );
    }
    print &ui_table_end();

    print &ui_hr();
    print &ui_subheading(L("SUB_SERVICES_PACKAGE_MGMT"));
    print "<p>" . L("MSG_SERVICES_PACKAGE_MGMT_NOTE") . "</p>";
    print "<p>";
    print &ui_link_icon("system.cgi?action=update&update_tab=freebsd", "FreeBSD Update", undef, { class => 'primary' });
    print " ";
    print &ui_link_icon("system.cgi?action=update&update_tab=pkg", "Package Update", undef, { class => 'primary' });
    print " ";
    print &ui_link_icon("system.cgi?action=update&update_tab=offline", "Offline Packages / Upload", undef, { class => 'primary' });
    print "</p>";
    print "<p><small>" . L("MSG_SERVICES_PACKAGE_MGMT_HINT") . "</small></p>";
}

sub action_service_control {
    my $service = $in{'service'};
    my $cmd = $in{'cmd'};

    my %allowed_cmd = map { $_ => 1 } qw(start stop restart);
    if (!$allowed_cmd{$cmd}) {
        print &ui_print_error(L("ERR_INVALID_SERVICE_COMMAND"));
        return &action_manage();
    }

    my %service_map = (
        'nfs' => 'nfsd',
        'smb' => 'smbd',
        'ssh' => 'sshd',
        'iscsi' => 'ctld',
    );
    my $service_cmd = $service_map{$service};
    if (!$service_cmd) {
        print &ui_print_error(L("ERR_INVALID_SERVICE"));
        return &action_manage();
    }

    my ($rc, $out, $err) = service_run($service_cmd, $cmd);
    
    if ($rc == 0) {
        log_info("Service $service: $cmd executed successfully");
        print &ui_print_success(L("SUCCESS_SERVICE_CMD", $cmd));
    } else {
        log_error("Service $service: $cmd failed - $err");
        print &ui_print_error(L("ERR_SERVICE_CMD_FAILED", $err));
    }
    
    &action_manage();
}

sub action_nfs {
    print &ui_subheading(L("SUB_NFS_CONFIG"));

    if ($in{'quick_nfs_mountd_reload'}) {
        my ($rc, $out, $err) = service_run('mountd', 'reload');
        if ($rc == 0) {
            print &ui_print_success("mountd reload executed.");
        } else {
            my ($rrc) = service_run('mountd', 'restart');
            if ($rrc == 0) {
                print &ui_print_success("mountd reload failed, restart executed instead.");
            } else {
                print &ui_print_error("mountd reload/restart failed: " . ($err || $out || 'unknown error'));
            }
        }
    }
    if ($in{'quick_nfs_nfsd_restart'}) {
        my ($rc, $out, $err) = service_run('nfsd', 'restart');
        if ($rc == 0) {
            print &ui_print_success("nfsd restart executed.");
        } else {
            print &ui_print_error("nfsd restart failed: " . ($err || $out || 'unknown error'));
        }
    }
    
    if ($in{'save_nfs'}) {
        eval {
            my $nfs_enabled = $in{'nfs_enabled'} ? 'YES' : 'NO';
            my $exports_txt = defined($in{'nfs_exports'}) ? $in{'nfs_exports'} : '';
            set_rc_conf_value($RC_CONF, 'nfs_server_enable', $nfs_enabled);
            my $backup = write_file_with_backup($EXPORTS_FILE, $exports_txt);

            if ($in{'restart_after_save'}) {
                my ($mrc) = service_run('mountd', 'reload');
                if ($mrc != 0) {
                    service_run('mountd', 'restart');
                }
                service_run('nfsd', 'restart');
            }

            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
            print &ui_print_success(L("SUCCESS_NFS_CONFIG_UPDATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_NFS_CONFIG_SAVE_FAILED", $@));
        }
    }

    my $exports_txt = read_file_text($EXPORTS_FILE);
    my $nfs_enabled = rc_conf_value($RC_CONF, 'nfs_server_enable') || 'NO';
    my $is_enabled_boot = ($nfs_enabled =~ /^(yes|on|true|1)$/i) ? 1 : 0;
    my $cfg_export_rows = parse_exports_rows($exports_txt);
    my $runtime_export_rows = parse_showmount_rows();
    my $export_rows = merge_export_rows($cfg_export_rows, $runtime_export_rows);
    my @svc_rows = (
        [ 'NFS daemon (nfsd)', service_state('nfsd') ],
        [ 'Mount daemon (mountd)', service_state('mountd') ],
        [ 'RPC bind (rpcbind)', service_state('rpcbind') ],
    );
    my $is_enabled_runtime = ($svc_rows[0] && $svc_rows[0][1] eq 'running') ? 1 : 0;
    my $is_enabled = ($is_enabled_boot || $is_enabled_runtime) ? 1 : 0;

    print &ui_table_start("NFS Service Status", "width=100%", 2, [
        "Service", "Status", "Details"
    ]);
    for my $row (@svc_rows) {
        my ($svc, $state, $raw_msg) = @$row;
        my $status =
            $state eq 'running' ? "<span class='zfsguru-status-ok'>" . L("VALUE_RUNNING") . "</span>" :
            $state eq 'stopped' ? "<span class='zfsguru-status-bad'>" . L("VALUE_STOPPED") . "</span>" :
                                  "<span class='zfsguru-status-unknown'>" . L("VALUE_UNKNOWN") . "</span>";
        my $details = first_status_line($raw_msg);
        print &ui_table_row(
            &html_escape($svc),
            $status,
            &html_escape($details || '-')
        );
    }
    print &ui_table_end();

    my $enabled_txt = $is_enabled_runtime ? 'running' : 'stopped';
    my $boot_txt = $is_enabled_boot ? 'enabled' : 'disabled';
    my $exports_count = scalar(@$export_rows);
    my $root_map_count = 0;
    my $net_rules = 0;
    for my $row (@$export_rows) {
        my $opt = lc($row->{options} || '');
        $root_map_count++ if $opt =~ /maproot|root=/;
        $net_rules++ if $opt =~ /-network|\snetwork=|\bnetwork\b/;
    }
    print &ui_columns_table(
        [ "Key", "Value", "Key", "Value" ],
        100,
        [
            [ "NFS service", &html_escape($enabled_txt), "Boot enable (rc.conf)", &html_escape($boot_txt) ],
            [ "Exports defined (runtime)", &html_escape($exports_count), "Network-scoped rules", &html_escape($net_rules) ],
            [ "Root mapping rules", &html_escape($root_map_count), "Restart after save (default)", "No" ],
        ],
        undef,
        1,
        "NFS Key Config Summary",
        L("VALUE_NONE")
    );

    print &ui_subheading("Quick Actions");
    print &ui_table_start("NFS Shortcuts", "width=100%", 2, [
        "Action", "Description"
    ]);
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=nfs&cmd=start'>Start NFS</a>",
        "Start nfsd service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=nfs&cmd=stop'>Stop NFS</a>",
        "Stop nfsd service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=nfs&cmd=restart'>Restart NFS</a>",
        "Restart nfsd service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=nfs&quick_nfs_mountd_reload=1'>Reload mountd</a>",
        "Reload export table without full NFS restart"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=nfs&quick_nfs_nfsd_restart=1'>Quick Restart nfsd</a>",
        "Immediate nfsd restart"
    );
    print &ui_table_row(
        "<a class='button' href='access.cgi?action=nfs&xnavigation=1'>NFS Access (datasets)</a>",
        "Per-dataset sharenfs control"
    );
    print &ui_table_end();
    
    print &ui_subheading("Quick NFS Edit");
    print &ui_form_start("services.cgi", "post");
    print &ui_hidden("action", "nfs");
    print &ui_hidden("save_nfs", 1);
    
    print &ui_table_start(L("TABLE_NFS_SETTINGS"), "width=100%", 2);
    print &ui_table_row(L("ROW_ENABLE_NFS"), &ui_checkbox("nfs_enabled", 1, L("OPT_ENABLED"), $is_enabled));
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($EXPORTS_FILE));
    print &ui_table_row(L("ROW_EXPORTS_CONTENT"), &ui_textarea("nfs_exports", $exports_txt, 10, 100));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    
    print &ui_subheading(L("SUB_NFS_EXPORTS"));
    print "<p>" . L("MSG_NFS_EXPORTS_HELP") . "</p>";
    if (@$export_rows) {
        my @cards;
        for my $row (@$export_rows) {
            my $path = &html_escape($row->{path} || '-');
            my $opts = &html_escape($row->{options} || '-');
            my $src  = &html_escape($row->{source} || 'unknown');
            my $card =
                "<div style='border:1px solid #d8dee6;border-radius:4px;padding:10px;min-height:94px;background:#f9fbfd'>" .
                "<div style='font-weight:700;margin-bottom:4px'>$path</div>" .
                "<div><small><b>Options:</b> $opts</small></div>" .
                "<div><small><b>Source:</b> $src</small></div>" .
                "</div>";
            push @cards, $card;
        }
        print &ui_grid_table(\@cards, 4, "100%");
    } else {
        print &ui_alert(L("VALUE_NONE"), "info");
    }
    
    print &ui_form_end([ [ "save_nfs", L("BTN_SAVE_NFS_CONFIG") ] ]);
}

sub action_smb {
    print &ui_subheading(L("SUB_SMB_CONFIG"));
    print "<p>This page is for SMB service status/control and quick edits. Full global Samba policy is in Access - Samba Settings, while per-share options are in Access - Samba Shares.</p>";
    
    if ($in{'save_smb'}) {
        eval {
            my %updates = (
                'workgroup'     => scalar($in{'smb_workgroup'} // ''),
                'server string' => scalar($in{'smb_server_string'} // ''),
                'wins server'   => scalar($in{'smb_wins_server'} // ''),
                'interfaces'    => scalar($in{'smb_interfaces'} // ''),
                'server role'   => scalar($in{'smb_server_role'} // 'standalone server'),
                'security'      => scalar($in{'smb_security'} // 'user'),
                'map to guest'  => scalar($in{'smb_map_to_guest'} // 'Never'),
                'guest ok'      => scalar($in{'smb_guest_ok'} // 'no'),
                'public'        => scalar($in{'smb_public'} // 'no'),
                'valid users'   => scalar($in{'smb_valid_users'} // ''),
                'invalid users' => scalar($in{'smb_invalid_users'} // ''),
                'create mask'   => scalar($in{'smb_create_mask'} // ''),
                'directory mask'=> scalar($in{'smb_directory_mask'} // ''),
            );
            my $raw = read_file_text($SMB_CONF);
            my $new_raw = update_ini_global_block($raw, \%updates);
            my $backup = write_file_with_backup($SMB_CONF, $new_raw);

            if ($in{'restart_after_save'}) {
                my ($rc) = service_run('smbd', 'restart');
                if ($rc != 0) {
                    service_run('samba_server', 'restart');
                }
            }

            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
            print &ui_print_success(L("SUCCESS_SMB_CONFIG_UPDATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SMB_CONFIG_SAVE_FAILED", $@));
        }
    }

    my $raw_conf = read_file_text($SMB_CONF);
    my $parsed = parse_ini_sections($raw_conf);
    my $global = $parsed->{sections}{global}{values} || {};

    my @svc_rows = (
        [ 'SMB (samba_server/smbd)', service_state([ 'samba_server', 'smbd' ]) ],
        [ 'NetBIOS (nmbd)',          service_state('nmbd') ],
        [ 'Winbind (winbindd)',      service_state('winbindd') ],
    );

    print &ui_table_start("SMB Service Status", "width=100%", 2, [
        "Service", "Status", "Details", "Actions"
    ]);
    for my $row (@svc_rows) {
        my ($svc, $state, $raw_msg) = @$row;
        my $status =
            $state eq 'running' ? "<span class='zfsguru-status-ok'>" . L("VALUE_RUNNING") . "</span>" :
            $state eq 'stopped' ? "<span class='zfsguru-status-bad'>" . L("VALUE_STOPPED") . "</span>" :
                                  "<span class='zfsguru-status-unknown'>" . L("VALUE_UNKNOWN") . "</span>";
        my $details = first_status_line($raw_msg);
        print &ui_table_row(
            &html_escape($svc),
            $status,
            &html_escape($details || '-'),
            ($svc eq 'smbd')
                ? "<a class='button' href='services.cgi?action=service_control&service=smb&cmd=start'>" . L("BTN_START") . "</a> " .
                  "<a class='button' href='services.cgi?action=service_control&service=smb&cmd=stop'>" . L("BTN_STOP") . "</a> " .
                  "<a class='button' href='services.cgi?action=service_control&service=smb&cmd=restart'>" . L("BTN_RESTART") . "</a>"
                : "-"
        );
    }
    print &ui_table_end();

    my %smb_def = (
        'workgroup' => 'WORKGROUP',
        'server string' => 'ZFSguru Server',
        'netbios name' => '',
        'server role' => 'standalone server',
        'security' => 'user',
        'map to guest' => 'Never',
        'guest account' => 'nobody',
        'log level' => '1',
        'wins server' => '',
        'interfaces' => '',
        'hosts allow' => '',
        'hosts deny' => '',
        'read only' => 'no',
        'browseable' => 'yes',
        'guest ok' => 'no',
        'public' => 'no',
        'valid users' => '',
        'invalid users' => '',
        'write list' => '',
        'read list' => '',
        'create mask' => '',
        'directory mask' => '0775',
        'force create mode' => '0000',
        'force directory mode' => '0000',
        'passdb backend' => 'tdbsam',
        'idmap config * : backend' => 'tdb',
        'idmap config * : range' => '70000-99999999',
        'case sensitive' => 'no',
        'default case' => 'lower',
        'preserve case' => 'yes',
        'short preserve case' => 'yes',
        'ea support' => 'yes',
        'vfs objects' => 'zfsacl',
        'nfs4:mode' => 'simple',
        'nfs4:acedup' => 'merge',
        'nfs4:chown' => 'yes',
        'map acl inherit' => 'yes',
        'disable netbios' => 'yes',
        'server smb encrypt' => 'auto',
        'inherit acls' => 'yes',
        'inherit permissions' => 'no',
        'dos filemode' => 'yes',
        'store dos attributes' => 'yes',
        'acl allow execute always' => 'yes',
        'load printers' => 'no',
        'printing' => 'bsd',
        'printcap name' => '/dev/null',
        'disable spoolss' => 'yes',
        'follow symlinks' => 'yes',
        'wide links' => 'no',
        'unix extensions' => 'no',
        'socket options' => '',
    );

    my @summary = (
        [ 'Shares defined', scalar(@{$parsed->{shares} || []}) ],
        [ 'workgroup', smb_global_or_default($global, 'workgroup', $smb_def{'workgroup'}) ],
        [ 'server string', smb_global_or_default($global, 'server string', $smb_def{'server string'}) ],
        [ 'netbios name', smb_global_or_default($global, 'netbios name', $smb_def{'netbios name'}) ],
        [ 'server role', smb_global_or_default($global, 'server role', $smb_def{'server role'}) ],
        [ 'security', smb_global_or_default($global, 'security', $smb_def{'security'}) ],
        [ 'map to guest', smb_global_or_default($global, 'map to guest', $smb_def{'map to guest'}) ],
        [ 'guest account', smb_global_or_default($global, 'guest account', $smb_def{'guest account'}) ],
        [ 'log level', smb_global_or_default($global, 'log level', $smb_def{'log level'}) ],
        [ 'wins server', smb_global_or_default($global, 'wins server', $smb_def{'wins server'}) ],
        [ 'interfaces', smb_global_or_default($global, 'interfaces', $smb_def{'interfaces'}) ],
        [ 'hosts allow', smb_global_or_default($global, 'hosts allow', $smb_def{'hosts allow'}) ],
        [ 'hosts deny', smb_global_or_default($global, 'hosts deny', $smb_def{'hosts deny'}) ],
        [ 'read only', smb_global_or_default($global, 'read only', $smb_def{'read only'}) ],
        [ 'browseable', smb_global_or_default($global, 'browseable', $smb_def{'browseable'}, 'browsable') ],
        [ 'guest ok', smb_global_or_default($global, 'guest ok', $smb_def{'guest ok'}) ],
        [ 'public', smb_global_or_default($global, 'public', $smb_def{'public'}) ],
        [ 'valid users', smb_global_or_default($global, 'valid users', $smb_def{'valid users'}) ],
        [ 'invalid users', smb_global_or_default($global, 'invalid users', $smb_def{'invalid users'}) ],
        [ 'write list', smb_global_or_default($global, 'write list', $smb_def{'write list'}) ],
        [ 'read list', smb_global_or_default($global, 'read list', $smb_def{'read list'}) ],
        [ 'create mask', smb_global_or_default($global, 'create mask', $smb_def{'create mask'}) ],
        [ 'directory mask', smb_global_or_default($global, 'directory mask', $smb_def{'directory mask'}) ],
        [ 'force create mode', smb_global_or_default($global, 'force create mode', $smb_def{'force create mode'}) ],
        [ 'force directory mode', smb_global_or_default($global, 'force directory mode', $smb_def{'force directory mode'}) ],
        [ 'passdb backend', smb_global_or_default($global, 'passdb backend', $smb_def{'passdb backend'}) ],
        [ 'idmap config * : backend', smb_global_or_default($global, 'idmap config * : backend', $smb_def{'idmap config * : backend'}) ],
        [ 'idmap config * : range', smb_global_or_default($global, 'idmap config * : range', $smb_def{'idmap config * : range'}) ],
        [ 'case sensitive', smb_global_or_default($global, 'case sensitive', $smb_def{'case sensitive'}) ],
        [ 'default case', smb_global_or_default($global, 'default case', $smb_def{'default case'}) ],
        [ 'preserve case', smb_global_or_default($global, 'preserve case', $smb_def{'preserve case'}) ],
        [ 'short preserve case', smb_global_or_default($global, 'short preserve case', $smb_def{'short preserve case'}) ],
        [ 'ea support', smb_global_or_default($global, 'ea support', $smb_def{'ea support'}) ],
        [ 'vfs objects', smb_global_or_default($global, 'vfs objects', $smb_def{'vfs objects'}) ],
        [ 'nfs4:mode', smb_global_or_default($global, 'nfs4:mode', $smb_def{'nfs4:mode'}) ],
        [ 'nfs4:acedup', smb_global_or_default($global, 'nfs4:acedup', $smb_def{'nfs4:acedup'}) ],
        [ 'nfs4:chown', smb_global_or_default($global, 'nfs4:chown', $smb_def{'nfs4:chown'}) ],
        [ 'map acl inherit', smb_global_or_default($global, 'map acl inherit', $smb_def{'map acl inherit'}) ],
        [ 'disable netbios', smb_global_or_default($global, 'disable netbios', $smb_def{'disable netbios'}) ],
        [ 'server smb encrypt', smb_global_or_default($global, 'server smb encrypt', $smb_def{'server smb encrypt'}) ],
        [ 'inherit acls', smb_global_or_default($global, 'inherit acls', $smb_def{'inherit acls'}) ],
        [ 'inherit permissions', smb_global_or_default($global, 'inherit permissions', $smb_def{'inherit permissions'}) ],
        [ 'dos filemode', smb_global_or_default($global, 'dos filemode', $smb_def{'dos filemode'}) ],
        [ 'store dos attributes', smb_global_or_default($global, 'store dos attributes', $smb_def{'store dos attributes'}) ],
        [ 'acl allow execute always', smb_global_or_default($global, 'acl allow execute always', $smb_def{'acl allow execute always'}) ],
        [ 'load printers', smb_global_or_default($global, 'load printers', $smb_def{'load printers'}) ],
        [ 'printing', smb_global_or_default($global, 'printing', $smb_def{'printing'}) ],
        [ 'printcap name', smb_global_or_default($global, 'printcap name', $smb_def{'printcap name'}) ],
        [ 'disable spoolss', smb_global_or_default($global, 'disable spoolss', $smb_def{'disable spoolss'}) ],
        [ 'follow symlinks', smb_global_or_default($global, 'follow symlinks', $smb_def{'follow symlinks'}) ],
        [ 'wide links', smb_global_or_default($global, 'wide links', $smb_def{'wide links'}) ],
        [ 'unix extensions', smb_global_or_default($global, 'unix extensions', $smb_def{'unix extensions'}) ],
        [ 'socket options', smb_global_or_default($global, 'socket options', $smb_def{'socket options'}) ],
    );

    my (@sum_rows, @cur);
    for my $pair (@summary) {
        my ($k, $v) = @$pair;
        $v = '(unset)' if !defined($v) || $v eq '';
        push @cur, &html_escape($k), &html_escape($v);
        if (@cur == 4) {
            push @sum_rows, [ @cur ];
            @cur = ();
        }
    }
    if (@cur) {
        push @cur, '-', '-' if @cur == 2;
        push @sum_rows, [ @cur ];
    }
    print &ui_columns_table(
        [ "Key", "Value", "Key", "Value" ],
        100,
        \@sum_rows,
        undef,
        1,
        "SMB Key Config Summary",
        L("VALUE_NONE")
    );

    print &ui_subheading("Quick Actions");
    print &ui_table_start("SMB Shortcuts", "width=100%", 2, [
        "Action", "Description"
    ]);
    print &ui_table_row(
        "<a class='button' href='access.cgi?action=smb_settings&xnavigation=1'>SMB Global Settings</a>",
        "Global Samba defaults and protocol tuning"
    );
    print &ui_table_row(
        "<a class='button' href='access.cgi?action=smb_shares&xnavigation=1'>SMB Shares</a>",
        "Create / modify shares and share-level permissions"
    );
    print &ui_table_row(
        "<a class='button' href='access.cgi?action=smb_users&xnavigation=1'>SMB Users</a>",
        "Manage Samba users (add/enable/disable/delete)"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=smb&cmd=restart'>Quick Restart SMB</a>",
        "Restart SMB service immediately"
    );
    print &ui_table_end();
    
    print &ui_subheading("Quick SMB Edit");
    print &ui_form_start("services.cgi", "post");
    print &ui_hidden("action", "smb");
    print &ui_hidden("save_smb", 1);
    
    print &ui_table_start(L("TABLE_SMB_SETTINGS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($SMB_CONF));
    print &ui_table_row(L("ROW_WORKGROUP"), &ui_textbox("smb_workgroup", $global->{'workgroup'} || 'WORKGROUP', 30));
    print &ui_table_row(L("ROW_SERVER_STRING"), &ui_textbox("smb_server_string", $global->{'server string'} || 'ZFSguru Server', 40));
    print &ui_table_row("Server Role", &ui_select("smb_server_role", ($global->{'server role'} || 'standalone server'), [
        [ 'standalone server', 'standalone server' ],
        [ 'member server', 'member server' ],
    ]));
    print &ui_table_row("Security", &ui_select("smb_security", ($global->{'security'} || 'user'), [
        [ 'user', 'user' ],
        [ 'share', 'share' ],
        [ 'domain', 'domain' ],
        [ 'ads', 'ads' ],
    ]));
    print &ui_table_row("Map to guest", &ui_select("smb_map_to_guest", ($global->{'map to guest'} || 'Never'), [
        [ 'Never', 'Never' ],
        [ 'Bad User', 'Bad User' ],
        [ 'Bad Password', 'Bad Password' ],
    ]));
    print &ui_table_row(L("ROW_WINS_SERVER"), &ui_textbox("smb_wins_server", $global->{'wins server'} || '', 30));
    print &ui_table_row(L("ROW_INTERFACES"), &ui_textbox("smb_interfaces", $global->{'interfaces'} || '', 40));
    print &ui_table_row("Guest OK", &ui_select("smb_guest_ok", ($global->{'guest ok'} || 'no'), [
        [ 'yes', L("OPT_YES") ],
        [ 'no', L("OPT_NO") ],
    ]));
    print &ui_table_row("Public", &ui_select("smb_public", ($global->{'public'} || 'no'), [
        [ 'yes', L("OPT_YES") ],
        [ 'no', L("OPT_NO") ],
    ]));
    print &ui_table_row("Valid users", &ui_textbox("smb_valid_users", $global->{'valid users'} || '', 40));
    print &ui_table_row("Invalid users", &ui_textbox("smb_invalid_users", $global->{'invalid users'} || '', 40));
    print &ui_table_row("Create mask", &ui_textbox("smb_create_mask", $global->{'create mask'} || '', 12));
    print &ui_table_row("Directory mask", &ui_textbox("smb_directory_mask", $global->{'directory mask'} || '0775', 12));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    
    print &ui_subheading(L("SUB_SMB_SHARES"));
    if (@{ $parsed->{shares} }) {
        my @cards;
        for my $share (@{ $parsed->{shares} }) {
            my $name = &html_escape($share->{name});
            my $path = &html_escape($share->{path} || '-');
            my $comment = &html_escape($share->{comment} || '-');
            my $card =
                "<div style='border:1px solid #d8dee6;border-radius:4px;padding:10px;min-height:94px;background:#f9fbfd'>" .
                "<div style='font-weight:700;margin-bottom:4px'>$name</div>" .
                "<div><small><b>Path:</b> $path</small></div>" .
                "<div><small><b>Comment:</b> $comment</small></div>" .
                "</div>";
            push @cards, $card;
        }
        print &ui_grid_table(\@cards, 4, "100%");
    } else {
        print &ui_alert(L("VALUE_NONE"), "info");
    }
    
    print &ui_form_end([ [ "save_smb", L("BTN_SAVE_SMB_CONFIG") ] ]);
}

sub action_ssh {
    print &ui_subheading(L("SUB_SSH_CONFIG"));
    
    if ($in{'save_ssh'}) {
        eval {
            my $allow_users = join_space_list(multi_input_values('ssh_allowusers'));
            my $deny_users = join_space_list(multi_input_values('ssh_denyusers'));
            my $allow_groups = join_space_list(multi_input_values('ssh_allowgroups'));
            my $deny_groups = join_space_list(multi_input_values('ssh_denygroups'));
            my %updates = (
                'Port'                 => scalar($in{'ssh_port'} || '22'),
                'PermitRootLogin'      => scalar($in{'ssh_root_login'} || 'no'),
                'PasswordAuthentication' => scalar($in{'ssh_passwd_auth'} || 'yes'),
                'PubkeyAuthentication' => scalar($in{'ssh_pubkey_auth'} || 'yes'),
                'PermitEmptyPasswords' => scalar($in{'ssh_empty_passwd'} || 'no'),
                'AllowUsers'           => $allow_users,
                'DenyUsers'            => $deny_users,
                'AllowGroups'          => $allow_groups,
                'DenyGroups'           => $deny_groups,
            );
            my $raw = read_file_text($SSHD_CONF);
            my $new_raw = update_sshd_config($raw, \%updates);
            my $backup = write_file_with_backup($SSHD_CONF, $new_raw);

            if ($in{'restart_after_save'}) {
                service_run('sshd', 'restart');
            }

            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
            print &ui_print_success(L("SUCCESS_SSH_CONFIG_UPDATED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SSH_CONFIG_SAVE_FAILED", $@));
        }
    }

    my $ssh_cfg = parse_sshd_config(read_file_text($SSHD_CONF));
    my $sys_users = system_users_list();
    my $sys_groups = system_groups_list();
    my %sel_allow_users = map { $_ => 1 } parse_space_list($ssh_cfg->{allowusers});
    my %sel_deny_users  = map { $_ => 1 } parse_space_list($ssh_cfg->{denyusers});
    my %sel_allow_groups = map { $_ => 1 } parse_space_list($ssh_cfg->{allowgroups});
    my %sel_deny_groups  = map { $_ => 1 } parse_space_list($ssh_cfg->{denygroups});
    my ($ssh_state, $ssh_state_raw) = service_state('sshd');
    my $ssh_status =
        $ssh_state eq 'running' ? "<span class='zfsguru-status-ok'>" . L("VALUE_RUNNING") . "</span>" :
        $ssh_state eq 'stopped' ? "<span class='zfsguru-status-bad'>" . L("VALUE_STOPPED") . "</span>" :
                                  "<span class='zfsguru-status-unknown'>" . L("VALUE_UNKNOWN") . "</span>";

    print &ui_table_start("SSH Service Status", "width=100%", 2, [
        "Service", "Status", "Details"
    ]);
    print &ui_table_row(
        "sshd",
        $ssh_status,
        &html_escape(first_status_line($ssh_state_raw) || '-')
    );
    print &ui_table_end();

    my $port = $ssh_cfg->{port} || '22';
    my $root = $ssh_cfg->{permitrootlogin} || 'no';
    my $pass = $ssh_cfg->{passwordauthentication} || 'yes';
    my $pubk = $ssh_cfg->{pubkeyauthentication} || 'yes';
    my $empt = $ssh_cfg->{permitemptypasswords} || 'no';
    my $listen = $ssh_cfg->{listenaddress} || '(default)';
    my $allow_users = $ssh_cfg->{allowusers} || '(unset)';
    my $deny_users = $ssh_cfg->{denyusers} || '(unset)';
    my $allow_groups = $ssh_cfg->{allowgroups} || '(unset)';
    my $deny_groups = $ssh_cfg->{denygroups} || '(unset)';

    print &ui_columns_table(
        [ "Key", "Value", "Key", "Value" ],
        100,
        [
            [ "Port", &html_escape($port), "PermitRootLogin", &html_escape($root) ],
            [ "PasswordAuthentication", &html_escape($pass), "PubkeyAuthentication", &html_escape($pubk) ],
            [ "PermitEmptyPasswords", &html_escape($empt), "ListenAddress", &html_escape($listen) ],
            [ "AllowUsers", &html_escape($allow_users), "DenyUsers", &html_escape($deny_users) ],
            [ "AllowGroups", &html_escape($allow_groups), "DenyGroups", &html_escape($deny_groups) ],
        ],
        undef,
        1,
        "SSH Key Config Summary",
        L("VALUE_NONE")
    );

    print &ui_subheading("Quick Actions");
    print &ui_table_start("SSH Shortcuts", "width=100%", 2, [
        "Action", "Description"
    ]);
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=ssh&cmd=start'>Start SSH</a>",
        "Start sshd service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=ssh&cmd=stop'>Stop SSH</a>",
        "Stop sshd service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=service_control&service=ssh&cmd=restart'>Restart SSH</a>",
        "Restart sshd service"
    );
    print &ui_table_row(
        "<a class='button' href='access.cgi?action=ssh&xnavigation=1'>SSH Access</a>",
        "Open SSH access overview"
    );
    print &ui_table_end();

    print &ui_subheading("Quick SSH Edit");
    print "<script type='text/javascript'>\n" .
          "function zfsguruSelectAll(id){var e=document.getElementById(id);if(!e)return;for(var i=0;i<e.options.length;i++){e.options[i].selected=true;}}\n" .
          "function zfsguruClearAll(id){var e=document.getElementById(id);if(!e)return;for(var i=0;i<e.options.length;i++){e.options[i].selected=false;}}\n" .
          "</script>\n";
    print &ui_alert(
        "Ctrl+click: add/remove one item. Shift+click: select a range. Ctrl+A: select all. " .
        "Unset: click the list and Ctrl+click selected items to clear all (no blue rows).",
        "info"
    );
    print &ui_form_start("services.cgi", "post");
    print &ui_hidden("action", "ssh");
    print &ui_hidden("save_ssh", 1);
    
    print &ui_table_start(L("TABLE_SSH_SETTINGS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($SSHD_CONF));
    print &ui_table_row(L("ROW_SSH_PORT"), &ui_textbox("ssh_port", ($ssh_cfg->{port} || '22'), 10));
    print &ui_table_row(L("ROW_ALLOW_ROOT_LOGIN"), &ui_select("ssh_root_login", ($ssh_cfg->{permitrootlogin} || 'no'), [
        [ "yes", L("OPT_YES") ],
        [ "no", L("OPT_NO") ],
        [ "without-password", L("OPT_WITHOUT_PASSWORD") ],
    ]));
    print &ui_table_row(L("ROW_PASSWORD_AUTH"), &ui_select("ssh_passwd_auth", ($ssh_cfg->{passwordauthentication} || 'yes'), [
        [ "yes", L("OPT_YES") ],
        [ "no", L("OPT_NO") ],
    ]));
    print &ui_table_row(L("ROW_PUBKEY_AUTH"), &ui_select("ssh_pubkey_auth", ($ssh_cfg->{pubkeyauthentication} || 'yes'), [
        [ "yes", L("OPT_YES") ],
        [ "no", L("OPT_NO") ],
    ]));
    print &ui_table_row(L("ROW_PERMIT_EMPTY_PASSWORDS"), &ui_select("ssh_empty_passwd", ($ssh_cfg->{permitemptypasswords} || 'no'), [
        [ "yes", L("OPT_YES") ],
        [ "no", L("OPT_NO") ],
    ]));
    print &ui_table_row(
        "AllowUsers",
        ui_multi_select_with_controls("ssh_allowusers", $sys_users, \%sel_allow_users, 8)
    );
    print &ui_table_row(
        "DenyUsers",
        ui_multi_select_with_controls("ssh_denyusers", $sys_users, \%sel_deny_users, 8)
    );
    print &ui_table_row(
        "AllowGroups",
        ui_multi_select_with_controls("ssh_allowgroups", $sys_groups, \%sel_allow_groups, 8)
    );
    print &ui_table_row(
        "DenyGroups",
        ui_multi_select_with_controls("ssh_denygroups", $sys_groups, \%sel_deny_groups, 8)
    );
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    
    print &ui_form_end([ [ "save_ssh", L("BTN_SAVE_SSH_CONFIG") ] ]);
}

sub action_iscsi {
    print &ui_subheading(L("SUB_ISCSI_CONFIG"));

    if ($in{'quick_iscsi_start'}) {
        my ($rc, $out, $err) = service_run('ctld', 'start');
        if ($rc == 0) {
            print &ui_print_success("ctld start executed.");
        } else {
            print &ui_print_error("ctld start failed: " . ($err || $out || 'unknown error'));
        }
    }
    if ($in{'quick_iscsi_stop'}) {
        my ($rc, $out, $err) = service_run('ctld', 'stop');
        if ($rc == 0) {
            print &ui_print_success("ctld stop executed.");
        } else {
            print &ui_print_error("ctld stop failed: " . ($err || $out || 'unknown error'));
        }
    }
    if ($in{'quick_iscsi_restart'}) {
        my ($rc, $out, $err) = service_run('ctld', 'restart');
        if ($rc == 0) {
            print &ui_print_success("ctld restart executed.");
        } else {
            print &ui_print_error("ctld restart failed: " . ($err || $out || 'unknown error'));
        }
    }

    my $prefill_backend = $in{'backend'} || '';
    if ($prefill_backend && $prefill_backend !~ m{^/dev/}) {
        $prefill_backend = "/dev/$prefill_backend";
    }
    my $prefill_target = $in{'target'} || '';
    if ($prefill_target && $prefill_target !~ /^[A-Za-z0-9:\.\-]+$/) {
        $prefill_target = '';
    }
    my $default_target = $prefill_target || ("iqn." . strftime("%Y-%m", localtime()) . ".zfsguru:target1");

    my $raw_ctl = read_file_text($CTL_CONF);
    my $iscsi_targets = parse_ctl_targets($raw_ctl);
    my %t_by_name = map { $_->{name} => $_ } @$iscsi_targets;

    # Backwards-compatible: if a target is passed for prefill but already exists,
    # show edit UI instead of the create form.
    if (!$in{'edit_target'} && !$in{'delete_target'} && !$in{'create_iscsi'} &&
        $prefill_target && exists $t_by_name{$prefill_target}) {
        $in{'edit_target'} = $prefill_target;
    }

    if ($in{'do_delete_target'}) {
        my $tname = $in{'delete_target'} || '';
        if (!$tname || $tname !~ /^[A-Za-z0-9:\.\-]+$/) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_TARGET"));
        } elsif (!$in{'confirm_delete_target'}) {
            print &ui_print_error(L("ERR_CONFIRM_DELETE_ISCSI_REQUIRED"));
            print &ui_alert(L("MSG_ISCSI_DELETE_WARNING"), "warning");
        } elsif (!ctl_target_exists($raw_ctl, $tname)) {
            print &ui_print_error(L("ERR_ISCSI_TARGET_NOT_FOUND", $tname));
        } else {
            eval {
                my ($new_raw, $removed) = remove_ctl_target_block($raw_ctl, $tname);
                die "Target not found in config" if !$removed;
                my $backup = write_file_with_backup($CTL_CONF, $new_raw);

                if ($in{'restart_after_save'}) {
                    service_run('ctld', 'restart');
                }

                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
                print &ui_print_success(L("SUCCESS_ISCSI_DELETED", $tname));
            };
            if ($@) {
                print &ui_print_error(L("ERR_ISCSI_DELETE_FAILED", $@));
            }
        }

        # Reload after any attempted delete
        $raw_ctl = read_file_text($CTL_CONF);
        $iscsi_targets = parse_ctl_targets($raw_ctl);
        %t_by_name = map { $_->{name} => $_ } @$iscsi_targets;
    }

    if ($in{'delete_target'} && !$in{'do_delete_target'}) {
        my $tname = $in{'delete_target'} || '';
        if (!$tname || $tname !~ /^[A-Za-z0-9:\.\-]+$/) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_TARGET"));
            return;
        }
        if (!exists $t_by_name{$tname}) {
            print &ui_print_error(L("ERR_ISCSI_TARGET_NOT_FOUND", $tname));
            return;
        }

        my $t = $t_by_name{$tname};
        print &ui_print_error_header(L("HDR_DESTRUCTIVE_OPERATION"));
        print "<p>" . L("MSG_ISCSI_DELETE_CONFIRM", &html_escape($tname)) . "</p>";
        print &ui_alert(L("MSG_ISCSI_DELETE_WARNING"), "warning");

        print &ui_form_start("services.cgi", "post");
        print &ui_hidden("action", "iscsi");
        print &ui_hidden("delete_target", $tname);
        print &ui_hidden("do_delete_target", 1);

        print &ui_table_start(L("TABLE_ISCSI_DELETE"), "width=100%", 2);
        print &ui_table_row(L("ROW_TARGET_NAME"), &html_escape($tname));
        print &ui_table_row(L("ROW_BACKEND_DEVICE"), &html_escape($t->{device} || '-'));
        print &ui_table_row(L("COL_LUN"), &html_escape(defined($t->{lun}) ? $t->{lun} : '0'));
        print &ui_table_row(L("ROW_CONFIRM_DELETE_ISCSI"),
            &ui_checkbox("confirm_delete_target", 1, L("LBL_CONFIRM_DELETE_ISCSI"), 0));
        print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"),
            &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
        print &ui_table_end();

        print &ui_form_end([
            [ "do_delete_target", L("BTN_DELETE") ],
        ]);
        print "<p><a class='button' href='services.cgi?action=iscsi'>" . L("BTN_CANCEL") . "</a></p>";
        return;
    }

    if ($in{'do_edit_target'}) {
        my $tname = $in{'edit_target'} || '';
        my $backend = $in{'edit_backend'} || '';
        my $lun = (defined($in{'edit_lun'}) && $in{'edit_lun'} =~ /^\d+$/) ? $in{'edit_lun'} : undef;
        my $orig_lun = (defined($in{'orig_lun'}) && $in{'orig_lun'} =~ /^\d+$/) ? $in{'orig_lun'} : undef;

        if (!$tname || $tname !~ /^[A-Za-z0-9:\.\-]+$/) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_TARGET"));
        } elsif ($backend !~ m{^/dev/[A-Za-z0-9/_\.\-]+$}) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_BACKEND"));
        } elsif (!defined $lun) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_LUN"));
        } else {
            eval {
                my $raw = read_file_text($CTL_CONF);
                die L("ERR_ISCSI_TARGET_NOT_FOUND", $tname) if !ctl_target_exists($raw, $tname);

                my $parsed = parse_ctl_targets($raw);
                my %by_name = map { $_->{name} => $_ } @$parsed;
                my $t = $by_name{$tname};
                die L("ERR_ISCSI_TARGET_NOT_FOUND", $tname) if !$t;

                my $cur_backend = $t->{device} || '';
                my $cur_lun = (defined($t->{lun}) && $t->{lun} =~ /^\d+$/) ? $t->{lun} : 0;
                die L("ERR_ISCSI_NO_CHANGES") if $cur_backend eq $backend && $cur_lun eq $lun;

                my ($new_raw, $changed, $found_lun) = update_ctl_target_block($raw, $tname, $orig_lun, $lun, $backend);
                die L("ERR_ISCSI_LUN_NOT_FOUND", defined($orig_lun) ? $orig_lun : '-') if !$found_lun;
                die L("ERR_ISCSI_NO_CHANGES") if !$changed;

                my $backup = write_file_with_backup($CTL_CONF, $new_raw);

                if ($in{'restart_after_save'}) {
                    service_run('ctld', 'restart');
                }

                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
                print &ui_print_success(L("SUCCESS_ISCSI_UPDATED", $tname));
            };
            if ($@) {
                print &ui_print_error(L("ERR_ISCSI_UPDATE_FAILED", $@));
            }
        }

        # Reload after any attempted edit
        $raw_ctl = read_file_text($CTL_CONF);
        $iscsi_targets = parse_ctl_targets($raw_ctl);
        %t_by_name = map { $_->{name} => $_ } @$iscsi_targets;
    }

    if ($in{'edit_target'} && !$in{'do_edit_target'}) {
        my $tname = $in{'edit_target'} || '';
        if (!$tname || $tname !~ /^[A-Za-z0-9:\.\-]+$/) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_TARGET"));
            return;
        }
        if (!exists $t_by_name{$tname}) {
            print &ui_print_error(L("ERR_ISCSI_TARGET_NOT_FOUND", $tname));
            return;
        }

        my $t = $t_by_name{$tname};
        my $cur_backend = $t->{device} || '';
        my $cur_lun = (defined($t->{lun}) && $t->{lun} =~ /^\d+$/) ? $t->{lun} : 0;
        my $edit_backend_default = $cur_backend;

        print &ui_subheading(L("SUB_EDIT_ISCSI_TARGET", &html_escape($tname)));
        if ($prefill_backend && $prefill_backend =~ m{^/dev/[A-Za-z0-9/_\.\-]+$} && $prefill_backend ne $cur_backend) {
            $edit_backend_default = $prefill_backend;
            print &ui_alert(L("MSG_ISCSI_PREFILL_BACKEND_NOTE", &html_escape($cur_backend || '-'), &html_escape($prefill_backend)), "info");
        }
        print &ui_alert(L("MSG_ISCSI_EDIT_WARNING"), "warning");

        my $preview = join("\n",
            "target $tname {",
            "    lun $cur_lun {",
            "        path " . ($cur_backend || '-'),
            "    }",
            "}",
        );
        print "<p>" . L("MSG_REVIEW_COMMAND") . "</p>";
        print "<pre class='zfsguru-code-block'>" . &html_escape($preview) . "</pre>";

        print &ui_form_start("services.cgi", "post");
        print &ui_hidden("action", "iscsi");
        print &ui_hidden("edit_target", $tname);
        print &ui_hidden("orig_lun", $cur_lun);
        print &ui_hidden("do_edit_target", 1);

        print &ui_table_start(L("TABLE_ISCSI_EDIT"), "width=100%", 2);
        print &ui_table_row(L("ROW_TARGET_NAME"), &html_escape($tname));
        print &ui_table_row(L("ROW_BACKEND_DEVICE"), &ui_textbox("edit_backend", $edit_backend_default, 40));
        print &ui_table_row(L("COL_LUN"), &ui_textbox("edit_lun", $cur_lun, 6));
        print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"),
            &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
        print &ui_table_end();

        print &ui_form_end([
            [ "do_edit_target", L("BTN_SAVE_CHANGES") ],
        ]);
        print "<p><a class='button' href='services.cgi?action=iscsi'>" . L("BTN_CANCEL") . "</a></p>";
        return;
    }

    if ($in{'create_iscsi'}) {
        my $target_name = $in{'iscsi_target_name'} || '';
        my $backend = $in{'iscsi_backend'} || '';
        my $lun = (defined($in{'iscsi_lun'}) && $in{'iscsi_lun'} =~ /^\d+$/) ? $in{'iscsi_lun'} : 0;

        if ($target_name !~ /^[A-Za-z0-9:\.\-]+$/) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_TARGET"));
        } elsif ($backend !~ m{^/dev/[A-Za-z0-9/_\.\-]+$}) {
            print &ui_print_error(L("ERR_ISCSI_INVALID_BACKEND"));
        } else {
            eval {
                my $raw = read_file_text($CTL_CONF);
                if (ctl_target_exists($raw, $target_name)) {
                    die L("ERR_ISCSI_TARGET_EXISTS", $target_name);
                }
                my $new_raw = append_ctl_target_block($raw, $target_name, $backend, $lun);
                my $backup = write_file_with_backup($CTL_CONF, $new_raw);

                if ($in{'restart_after_save'}) {
                    service_run('ctld', 'restart');
                }

                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
                print &ui_print_success(L("SUCCESS_ISCSI_CREATED"));
            };
            if ($@) {
                print &ui_print_error(L("ERR_ISCSI_CONFIG_SAVE_FAILED", $@));
            }
        }
    }

    $iscsi_targets = parse_ctl_targets(read_file_text($CTL_CONF));

    my ($ctld_state, $ctld_raw) = service_state('ctld');
    my $ctld_status =
        $ctld_state eq 'running' ? "<span class='zfsguru-status-ok'>" . L("VALUE_RUNNING") . "</span>" :
        $ctld_state eq 'stopped' ? "<span class='zfsguru-status-bad'>" . L("VALUE_STOPPED") . "</span>" :
                                   "<span class='zfsguru-status-unknown'>" . L("VALUE_UNKNOWN") . "</span>";
    print &ui_table_start("iSCSI Service Status", "width=100%", 2, [
        "Service", "Status", "Details"
    ]);
    print &ui_table_row(
        "ctld",
        $ctld_status,
        &html_escape(first_status_line($ctld_raw) || '-')
    );
    print &ui_table_end();

    my %uniq_backend;
    my $max_lun = 0;
    for my $t (@$iscsi_targets) {
        my $dev = $t->{device} || '';
        $uniq_backend{$dev} = 1 if length $dev;
        my $lun = (defined($t->{lun}) && $t->{lun} =~ /^\d+$/) ? $t->{lun} : 0;
        $max_lun = $lun if $lun > $max_lun;
    }
    my $targets_count = scalar(@$iscsi_targets);
    my $backend_count = scalar(keys %uniq_backend);
    print &ui_columns_table(
        [ "Key", "Value", "Key", "Value" ],
        100,
        [
            [ "iSCSI service", &html_escape($ctld_state), "Config file", &html_escape($CTL_CONF) ],
            [ "Targets defined", &html_escape($targets_count), "Unique backends", &html_escape($backend_count) ],
            [ "Max LUN id", &html_escape($max_lun), "Restart after save (default)", "No" ],
        ],
        undef,
        1,
        "iSCSI Key Config Summary",
        L("VALUE_NONE")
    );

    print &ui_subheading("Quick Actions");
    print &ui_table_start("iSCSI Shortcuts", "width=100%", 2, [
        "Action", "Description"
    ]);
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=iscsi&quick_iscsi_start=1'>Start iSCSI</a>",
        "Start ctld service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=iscsi&quick_iscsi_stop=1'>Stop iSCSI</a>",
        "Stop ctld service"
    );
    print &ui_table_row(
        "<a class='button' href='services.cgi?action=iscsi&quick_iscsi_restart=1'>Restart iSCSI</a>",
        "Restart ctld service"
    );
    print &ui_table_row(
        "<a class='button' href='access.cgi?action=iscsi&xnavigation=1'>iSCSI Access</a>",
        "Open iSCSI access overview"
    );
    print &ui_table_end();

    print &ui_table_start(L("TABLE_ISCSI_TARGETS"), "width=100%", 2, [
        L("COL_TARGET_NAME"), L("COL_DEVICE"), L("COL_LUN"), L("COL_ACTIONS")
    ]);
    if (@$iscsi_targets) {
        for my $t (@$iscsi_targets) {
            my $edit = "<a class='button' href='services.cgi?action=iscsi&edit_target=" .
                &url_encode($t->{name}) . "'>" . L("BTN_EDIT") . "</a>";
            my $del = "<a class='button' href='services.cgi?action=iscsi&delete_target=" .
                &url_encode($t->{name}) . "'>" . L("BTN_DELETE") . "</a>";
            print &ui_table_row(
                &html_escape($t->{name}),
                &html_escape($t->{device} || '-'),
                &html_escape($t->{lun} || '0'),
                "$edit $del"
            );
        }
    } else {
        print &ui_table_row("-", "-", "-", "-");
    }
    print &ui_table_end();
    
    print &ui_hr();
    print &ui_subheading(L("SUB_CREATE_ISCSI"));
    
    print &ui_form_start("services.cgi", "post");
    print &ui_hidden("action", "iscsi");
    print &ui_hidden("create_iscsi", 1);
    
    print &ui_table_start(L("TABLE_NEW_ISCSI_TARGET"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($CTL_CONF));
    print &ui_table_row(L("ROW_TARGET_NAME"), &ui_textbox("iscsi_target_name", $default_target, 50));
    print &ui_table_row(L("ROW_BACKEND_DEVICE"), &ui_textbox("iscsi_backend", $prefill_backend, 40));
    print &ui_table_row(L("COL_LUN"), &ui_textbox("iscsi_lun", "0", 6));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    
    print &ui_form_end([ [ "create_iscsi", L("BTN_CREATE_TARGET") ] ]);
}

sub first_status_line {
    my ($txt) = @_;
    return '' unless defined $txt && length $txt;
    for my $line (split /\n/, $txt) {
        next unless defined $line;
        $line =~ s/^\s+|\s+$//g;
        next unless length $line;
        return substr($line, 0, 160);
    }
    return '';
}

sub smb_global_or_default {
    my ($global, $key, $default, @aliases) = @_;
    $global = {} unless ref($global) eq 'HASH';
    for my $name ($key, @aliases) {
        next unless defined $name;
        my $lk = lc($name);
        if (exists $global->{$lk} && defined $global->{$lk} && length $global->{$lk}) {
            return $global->{$lk};
        }
    }
    return $default;
}

sub service_state {
    my ($service_name) = @_;
    my @candidates = ref($service_name) eq 'ARRAY' ? @$service_name : ($service_name);
    my ($best_state, $best_txt) = ('unknown', '');

    for my $svc (@candidates) {
        next unless defined $svc && length $svc;
        my ($rc, $out, $err) = service_run($svc, 'status');
        my $txt = join("\n", grep { defined $_ && length $_ } ($out, $err));
        my $lc = lc($txt || '');

        return ('running', $txt) if $rc == 0 || $lc =~ /\bis running\b|running as pid|active\s*\(running\)/;

        if ($lc =~ /does not exist|not found|unknown service|no such file|not installed/) {
            if ($best_state eq 'unknown') {
                $best_state = 'stopped';
                $best_txt = $txt;
            }
            next;
        }
        if ($lc =~ /not running|isn't running|is not running|stopped|not started|inactive/) {
            $best_state = 'stopped';
            $best_txt = $txt;
            next;
        }
        if ($best_state eq 'unknown') {
            $best_txt = $txt;
        }
    }

    return ($best_state, $best_txt);
}

sub parse_exports_rows {
    my ($raw) = @_;
    my @rows;
    for my $line (split /\n/, ($raw || '')) {
        $line =~ s/\s+#.*$//;
        $line =~ s/^\s+|\s+$//g;
        next unless length $line;
        next if $line =~ /^\s*#/;
        my ($path, @opts) = split /\s+/, $line;
        next unless defined $path && length $path;
        push @rows, {
            path => $path,
            options => @opts ? join(' ', @opts) : '-',
        };
    }
    return \@rows;
}

sub parse_showmount_rows {
    my @cmds = (
        [ '/sbin/showmount', '-e', 'localhost' ],
        [ '/usr/sbin/showmount', '-e', 'localhost' ],
        [ 'showmount', '-e', 'localhost' ],
    );
    my @rows;
    my %seen;

    for my $cmd (@cmds) {
        my ($rc, $out, $err) = run_cmd(@$cmd);
        next if $rc != 0 || !defined($out) || $out !~ /\S/;
        for my $line (split /\n/, $out) {
            next if $line =~ /^\s*Exports list on /i;
            next if $line =~ /^\s*$/;
            my ($path, @rest) = split /\s+/, $line;
            next unless defined($path) && $path =~ m{^/};
            my $opts = @rest ? join(' ', @rest) : '-';
            my $key = lc($path) . "|" . lc($opts);
            next if $seen{$key}++;
            push @rows, { path => $path, options => $opts, source => 'showmount' };
        }
        last if @rows;
    }
    return \@rows;
}

sub merge_export_rows {
    my ($cfg_rows, $runtime_rows) = @_;
    my @rows;
    my %seen;

    for my $row (@{ $runtime_rows || [] }) {
        next unless ref($row) eq 'HASH';
        my $path = $row->{path} || '';
        my $opt  = $row->{options} || '-';
        next unless $path ne '';
        my $key = lc($path) . "|" . lc($opt);
        next if $seen{$key}++;
        push @rows, { path => $path, options => $opt, source => 'showmount' };
    }

    for my $row (@{ $cfg_rows || [] }) {
        next unless ref($row) eq 'HASH';
        my $path = $row->{path} || '';
        my $opt  = $row->{options} || '-';
        next unless $path ne '';
        my $key = lc($path) . "|" . lc($opt);
        next if $seen{$key}++;
        push @rows, { path => $path, options => $opt, source => 'config (/etc/exports)' };
    }

    @rows = sort {
        lc($a->{path} || '') cmp lc($b->{path} || '')
            ||
        lc($a->{options} || '') cmp lc($b->{options} || '')
    } @rows;

    return \@rows;
}

sub parse_ini_sections {
    my ($raw) = @_;
    my %sections;
    my @order;
    my $cur = '';
    $sections{$cur} = { values => {} };

    for my $line (split /\n/, ($raw || '')) {
        if ($line =~ /^\s*\[([^\]]+)\]\s*$/) {
            $cur = lc($1);
            $cur =~ s/^\s+|\s+$//g;
            if (!exists $sections{$cur}) {
                $sections{$cur} = { values => {} };
                push @order, $cur;
            }
            next;
        }
        next if $line =~ /^\s*[#;]/;
        next unless $line =~ /^\s*([^=]+?)\s*=\s*(.*?)\s*$/;
        my ($k, $v) = (lc($1), $2);
        $k =~ s/^\s+|\s+$//g;
        $sections{$cur}{values}{$k} = $v;
    }

    my @shares;
    for my $sec (@order) {
        next if $sec eq 'global';
        my $vals = $sections{$sec}{values} || {};
        push @shares, {
            name => $sec,
            path => $vals->{path} || '',
            comment => $vals->{comment} || '',
        };
    }

    return {
        sections => \%sections,
        order    => \@order,
        shares   => \@shares,
    };
}

sub update_ini_global_block {
    my ($raw, $updates) = @_;
    my @keys = (
        'workgroup',
        'server string',
        'wins server',
        'interfaces',
        'server role',
        'security',
        'map to guest',
        'guest ok',
        'public',
        'valid users',
        'invalid users',
        'create mask',
        'directory mask',
    );
    my @lines = split /\n/, ($raw || ''), -1;

    my ($start, $end);
    for my $i (0 .. $#lines) {
        next unless $lines[$i] =~ /^\s*\[\s*global\s*\]\s*$/i;
        $start = $i;
        $end = $#lines;
        for my $j ($i + 1 .. $#lines) {
            if ($lines[$j] =~ /^\s*\[[^\]]+\]\s*$/) {
                $end = $j - 1;
                last;
            }
        }
        last;
    }

    if (!defined $start) {
        my @hdr = ('[global]');
        for my $k (@keys) {
            next unless defined $updates->{$k} && length $updates->{$k};
            push @hdr, "\t$k = $updates->{$k}";
        }
        push @hdr, '';
        my $prefix = join("\n", @hdr);
        return length($raw || '') ? ($prefix . "\n" . $raw) : ($prefix . "\n");
    }

    my @block = ();
    if ($end >= $start + 1) {
        @block = @lines[$start + 1 .. $end];
    }

    for my $k (@keys) {
        @block = grep { $_ !~ /^\s*\Q$k\E\s*=/i } @block;
        next unless defined $updates->{$k} && length $updates->{$k};
        push @block, "\t$k = $updates->{$k}";
    }

    my @new_lines = (
        @lines[0 .. $start],
        @block,
        @lines[$end + 1 .. $#lines],
    );
    my $new_raw = join("\n", @new_lines);
    $new_raw .= "\n" if $new_raw !~ /\n\z/;
    return $new_raw;
}

sub parse_sshd_config {
    my ($raw) = @_;
    my %cfg;
    for my $line (split /\n/, ($raw || '')) {
        next if $line =~ /^\s*#/;
        next unless $line =~ /^\s*(\S+)\s+(.+?)\s*$/;
        my ($k, $v) = (lc($1), $2);
        $cfg{$k} = $v;
    }
    return \%cfg;
}

sub update_sshd_config {
    my ($raw, $updates) = @_;
    my @order = (
        'Port',
        'PermitRootLogin',
        'PasswordAuthentication',
        'PubkeyAuthentication',
        'PermitEmptyPasswords',
        'AllowUsers',
        'DenyUsers',
        'AllowGroups',
        'DenyGroups',
    );

    my @lines = split /\n/, ($raw || ''), -1;
    for my $k (@order) {
        my $v = exists $updates->{$k} ? $updates->{$k} : undef;
        @lines = grep { /^\s*#/ || $_ !~ /^\s*\Q$k\E\s+/i } @lines;
        next unless defined $v && length $v;
        push @lines, "$k $v";
    }

    my $new_raw = join("\n", @lines);
    $new_raw .= "\n" if $new_raw !~ /\n\z/;
    return $new_raw;
}

sub parse_space_list {
    my ($raw) = @_;
    return () unless defined $raw && length $raw;
    my @parts = split(/[,\s]+/, $raw);
    my %seen;
    my @out;
    for my $p (@parts) {
        next unless defined $p;
        $p =~ s/^\s+|\s+$//g;
        next unless $p =~ /^[A-Za-z0-9._@:-]+$/;
        next if $seen{$p}++;
        push @out, $p;
    }
    return @out;
}

sub multi_input_values {
    my ($name) = @_;
    my $raw = $in{$name};
    return () unless defined $raw && length $raw;
    $raw =~ s/\0/ /g;
    return parse_space_list($raw);
}

sub join_space_list {
    my (@vals) = @_;
    return '' unless @vals;
    return join(' ', @vals);
}

sub system_users_list {
    my %seen;
    my @out;
    eval {
        setpwent();
        while (my @pw = getpwent()) {
            my $u = $pw[0];
            next unless defined $u && $u =~ /^[A-Za-z0-9._-]{1,64}$/;
            next if $seen{$u}++;
            push @out, $u;
        }
        endpwent();
    };
    @out = sort { lc($a) cmp lc($b) } @out;
    return \@out;
}

sub system_groups_list {
    my %seen;
    my @out;
    eval {
        setgrent();
        while (my @gr = getgrent()) {
            my $g = $gr[0];
            next unless defined $g && $g =~ /^[A-Za-z0-9._-]{1,64}$/;
            next if $seen{$g}++;
            push @out, $g;
        }
        endgrent();
    };
    @out = sort { lc($a) cmp lc($b) } @out;
    return \@out;
}

sub ui_multi_select_html {
    my ($name, $items, $selected, $size) = @_;
    $items = [] unless ref($items) eq 'ARRAY';
    $selected = {} unless ref($selected) eq 'HASH';
    $size ||= 8;
    my $html = "<select name='" . &html_escape($name) . "' multiple size='" . int($size) . "' style='min-width:280px'>";
    for my $it (@$items) {
        next unless defined $it;
        my $sel = $selected->{$it} ? " selected" : "";
        $html .= "<option value='" . &html_escape($it) . "'$sel>" . &html_escape($it) . "</option>";
    }
    $html .= "</select>";
    return $html;
}

sub ui_multi_select_with_controls {
    my ($name, $items, $selected, $size) = @_;
    my $id = $name;
    $id =~ s/[^A-Za-z0-9_]/_/g;
    my $select = ui_multi_select_html($name, $items, $selected, $size);
    $select =~ s/<select /<select id='$id' /;

    return $select .
        "<div style='margin-top:4px'>" .
        "<button type='button' onclick=\"zfsguruSelectAll('$id'); return false;\">Select all</button> " .
        "<button type='button' onclick=\"zfsguruClearAll('$id'); return false;\">Clear</button>" .
        "</div>";
}

sub ctl_target_exists {
    my ($raw, $target_name) = @_;
    return 0 unless defined $raw && defined $target_name;
    return ($raw =~ /^\s*target\s+\Q$target_name\E\s*\{/m) ? 1 : 0;
}

sub append_ctl_target_block {
    my ($raw, $target_name, $backend, $lun) = @_;
    my $block = join("\n",
        "target $target_name {",
        "    auth-group no-authentication",
        "    portal-group default",
        "    lun $lun {",
        "        path $backend",
        "    }",
        "}",
        "",
    );

    my $new_raw = $raw || '';
    $new_raw .= "\n" if length($new_raw) && $new_raw !~ /\n\z/;
    $new_raw .= $block;
    return $new_raw;
}

sub remove_ctl_target_block {
    my ($raw, $target_name) = @_;
    return ($raw || '', 0) unless defined $target_name && length $target_name;

    my @lines = split /\n/, ($raw || ''), -1;
    my @out;
    my $removed = 0;
    my $in_block = 0;
    my $depth = 0;

    for my $line (@lines) {
        if (!$in_block) {
            if ($line =~ /^\s*target\s+\Q$target_name\E\s*\{/) {
                $in_block = 1;
                $removed = 1;
                $depth = 0;
                $depth += () = ($line =~ /\{/g);
                $depth -= () = ($line =~ /\}/g);
                $in_block = 0 if $depth <= 0;
                next;
            }
            push @out, $line;
            next;
        }

        $depth += () = ($line =~ /\{/g);
        $depth -= () = ($line =~ /\}/g);
        if ($depth <= 0) {
            $in_block = 0;
            $depth = 0;
        }
        next;
    }

    my $new_raw = join("\n", @out);
    $new_raw .= "\n" if length($new_raw) && $new_raw !~ /\n\z/;
    return ($new_raw, $removed);
}

sub update_ctl_target_block {
    my ($raw, $target_name, $orig_lun, $new_lun, $new_backend) = @_;
    return ($raw || '', 0, 0) unless defined $target_name && length $target_name;

    my @lines = split /\n/, ($raw || ''), -1;
    my @out;
    my $changed = 0;
    my $found_lun = 0;

    my $in_block = 0;
    my $depth = 0;
    my @block;

    for my $line (@lines) {
        if (!$in_block) {
            if ($line =~ /^\s*target\s+\Q$target_name\E\s*\{/) {
                $in_block = 1;
                $depth = 0;
                @block = ($line);
                $depth += () = ($line =~ /\{/g);
                $depth -= () = ($line =~ /\}/g);
                if ($depth <= 0) {
                    my ($new_block, $chg, $found) = _ctl_edit_target_block(\@block, $orig_lun, $new_lun, $new_backend);
                    push @out, @$new_block;
                    $changed ||= $chg;
                    $found_lun ||= $found;
                    $in_block = 0;
                    $depth = 0;
                    @block = ();
                }
                next;
            }
            push @out, $line;
            next;
        }

        push @block, $line;
        $depth += () = ($line =~ /\{/g);
        $depth -= () = ($line =~ /\}/g);
        if ($depth <= 0) {
            my ($new_block, $chg, $found) = _ctl_edit_target_block(\@block, $orig_lun, $new_lun, $new_backend);
            push @out, @$new_block;
            $changed ||= $chg;
            $found_lun ||= $found;
            $in_block = 0;
            $depth = 0;
            @block = ();
        }
    }

    # Malformed config; preserve leftover block verbatim
    if ($in_block && @block) {
        push @out, @block;
    }

    my $new_raw = join("\n", @out);
    $new_raw .= "\n" if length($new_raw) && $new_raw !~ /\n\z/;
    return ($new_raw, $changed, $found_lun);
}

sub _ctl_edit_target_block {
    my ($lines_ref, $orig_lun, $new_lun, $new_backend) = @_;
    my @lines = @$lines_ref;
    my @out;
    my $changed = 0;

    my $target_lun;
    if (defined $orig_lun && $orig_lun =~ /^\d+$/) {
        $target_lun = $orig_lun;
    }

    my $in_lun = 0;
    my $lun_depth = 0;
    my $this_is_target = 0;
    my $path_updated = 0;
    my $lun_content_indent = "        ";
    my $found_target_lun = 0;

    for my $line (@lines) {
        if (!$in_lun && $line =~ /^(\s*)lun\s+(\d+)\s*\{/) {
            my ($indent, $lun) = ($1, $2);
            $lun_content_indent = $indent . "    ";
            $path_updated = 0;
            $in_lun = 1;
            $lun_depth = 0;
            $lun_depth += () = ($line =~ /\{/g);
            $lun_depth -= () = ($line =~ /\}/g);

            # If no orig_lun was provided, fall back to the first lun block.
            if (!defined $target_lun) {
                $target_lun = $lun;
            }

            $this_is_target = ($lun eq $target_lun) ? 1 : 0;
            $found_target_lun ||= $this_is_target;

            if ($this_is_target && defined($new_lun) && $new_lun =~ /^\d+$/ && $new_lun ne $lun) {
                $line = "${indent}lun $new_lun {";
                $changed = 1;
            }

            push @out, $line;

            if ($lun_depth <= 0) {
                # Avoid getting stuck in lun mode on malformed one-line blocks.
                $in_lun = 0;
                $this_is_target = 0;
                $lun_depth = 0;
            }
            next;
        }

        if ($in_lun) {
            if ($this_is_target && !$path_updated && $line =~ /^(\s*)path\s+\S+/) {
                my $pindent = $1;
                my $new_line = "${pindent}path $new_backend";
                if ($line ne $new_line) {
                    $line = $new_line;
                    $changed = 1;
                }
                $path_updated = 1;
            }

            my $delta = 0;
            $delta += () = ($line =~ /\{/g);
            $delta -= () = ($line =~ /\}/g);

            # End of lun block?
            if ($lun_depth + $delta <= 0) {
                if ($this_is_target && !$path_updated) {
                    push @out, "${lun_content_indent}path $new_backend";
                    $changed = 1;
                    $path_updated = 1;
                }
                push @out, $line;
                $in_lun = 0;
                $lun_depth = 0;
                $this_is_target = 0;
                next;
            } else {
                push @out, $line;
                $lun_depth += $delta;
                next;
            }
        }

        push @out, $line;
    }

    return (\@out, $changed, $found_target_lun);
}

1;
