#!/usr/bin/env perl

package main;

use strict;
use warnings;
use POSIX qw(strftime);
use File::Basename qw(basename);
use Sys::Hostname;
use IPC::Open3;
use Symbol qw(gensym);
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
my $EXPORTS_FILE = '/etc/exports';
my $SMB_CONF     = '/usr/local/etc/smb4.conf';
my $SSHD_CONF    = '/etc/ssh/sshd_config';
my $CTL_CONF     = '/etc/ctl.conf';
my $BACKUP_DIR   = '/var/tmp/zfsguru-config-backups';

zfsguru_page_header(title_key => "TITLE_ACCESS");

eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'smb_shares';

my %tab_feature = (
    smb_shares   => 'access_smb',
    smb_users    => 'access_smb',
    smb_settings => 'access_smb',
    nfs          => 'access_nfs',
    ssh          => 'access_ssh',
    iscsi        => 'access_iscsi',
);

my $base_access = acl_feature_allowed('access');
my $tab_feat = $tab_feature{$action};
if (!$base_access && (!$tab_feat || !acl_feature_allowed($tab_feat))) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'access'));
    zfsguru_page_footer();
    exit 0;
}

my @tabs_list = ();
push @tabs_list, [ 'smb_shares',   'TAB_SMB_SHARES' ]   if $base_access || acl_feature_allowed('access_smb');
push @tabs_list, [ 'smb_users',    'TAB_SMB_USERS' ]    if $base_access || acl_feature_allowed('access_smb');
push @tabs_list, [ 'smb_settings', 'TAB_SMB_SETTINGS' ] if $base_access || acl_feature_allowed('access_smb');
push @tabs_list, [ 'nfs',          'TAB_NFS_ACCESS' ]   if $base_access || acl_feature_allowed('access_nfs');
push @tabs_list, [ 'ssh',          'TAB_SSH_ACCESS' ]   if $base_access || acl_feature_allowed('access_ssh');
push @tabs_list, [ 'iscsi',        'TAB_ISCSI_ACCESS' ] if $base_access || acl_feature_allowed('access_iscsi');

print zfsguru_print_tabs(
    script => 'access.cgi',
    active => $action,
    tabs   => \@tabs_list,
);

my $default_tab = @tabs_list ? $tabs_list[0][0] : 'smb_shares';

if ($action eq 'smb_shares') {
    action_smb_shares();
} elsif ($action eq 'smb_users') {
    action_smb_users();
} elsif ($action eq 'smb_settings') {
    action_smb_settings();
} elsif ($action eq 'nfs') {
    action_nfs_access();
} elsif ($action eq 'ssh') {
    action_ssh_access();
} elsif ($action eq 'iscsi') {
    action_iscsi_access();
}

my $back_url = 'index.cgi';
if ($action ne $default_tab) {
    $back_url = "access.cgi?action=$default_tab";
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_smb_shares {
    print &ui_subheading(L("SUB_SMB_SHARES"));
    print "<p>" . L("MSG_SMB_SHARES_HELP") . "</p>";

    my $pdbedit = has_command('pdbedit') || '/usr/local/bin/pdbedit';
    my $smb_users = smb_users_info($pdbedit);
    my @smb_user_opts = map { [ $_->{name}, $_->{name} ] } @{ $smb_users || [] };
    my %smb_user_set = map { $_->{name} => 1 } @{ $smb_users || [] };

    if ($in{'delete_share'}) {
        my $name = $in{'share_name'} || '';
        if ($name !~ /^[A-Za-z0-9._-]{1,32}$/) {
            print &ui_print_error(L("ERR_SMB_INVALID_SHARE"));
        } else {
            eval {
                my $raw = read_file_text($SMB_CONF);
                my $new_raw = ini_remove_section($raw, $name);
                my $backup = write_file_with_backup($SMB_CONF, $new_raw);
                print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
                print &ui_print_success(L("SUCCESS_SMB_SHARE_REMOVED", $name));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SMB_CONFIG_SAVE_FAILED", $@));
            }
        }
    }

    my $edit_share = '';
    $edit_share = $in{'share_name'} || '' if $in{'edit_share'};
    $edit_share =~ s/^\s+|\s+$//g;

    if ($in{'save_share'} || $in{'create_share'}) {
        my $original_name = $in{'original_share_name'} || '';
        $original_name =~ s/^\s+|\s+$//g;
        my $name = $in{'new_share_name'} || '';
        my $path = $in{'new_share_path'} || '';
        my $comment = $in{'new_share_comment'} || '';
        my $read_only = $in{'new_share_readonly'} ? 'yes' : 'no';
        my $browseable = $in{'new_share_browseable'} ? 'yes' : 'no';
        my $guest = $in{'new_share_guest'} ? 'yes' : 'no';
        my $public = $in{'new_share_public'} ? 'yes' : 'no';
        my $mask_mode = $in{'new_share_mask_mode'} || 'none';

        my @write_list = parse_multi_select_values($in{'new_share_write_list'});
        my @read_list  = parse_multi_select_values($in{'new_share_read_list'});

        my $input_error = '';
        my ($create_mask, $directory_mask) = ('', '');
        if ($mask_mode eq 'preset_644_775') {
            $create_mask = '0644';
            $directory_mask = '0775';
        } elsif ($mask_mode eq 'preset_755_775') {
            $create_mask = '0755';
            $directory_mask = '0775';
        } elsif ($mask_mode eq 'custom') {
            $create_mask = normalize_smb_mask($in{'new_share_create_mask'});
            $directory_mask = normalize_smb_mask($in{'new_share_directory_mask'});
        } elsif ($mask_mode ne 'none') {
            $input_error = L("ERR_SMB_MASK_MODE_INVALID");
        }

        if ($name !~ /^[A-Za-z0-9._-]{1,32}$/) {
            print &ui_print_error(L("ERR_SMB_INVALID_SHARE"));
        } elsif ($path !~ m{^/}) {
            print &ui_print_error(L("ERR_SMB_INVALID_PATH"));
        } elsif ($input_error) {
            print &ui_print_error($input_error);
        } elsif ($mask_mode eq 'custom' && (!$create_mask || !$directory_mask)) {
            print &ui_print_error(L("ERR_SMB_MASK_INVALID"));
        } else {
            for my $u (@write_list, @read_list) {
                if (!$smb_user_set{$u}) {
                    $input_error = L("ERR_SMB_USER_INVALID", $u);
                    last;
                }
            }
            if ($input_error) {
                print &ui_print_error($input_error);
            } else {
                my %section = (
                    'path' => $path,
                    'comment' => $comment,
                    'read only' => $read_only,
                    'browseable' => $browseable,
                    'guest ok' => $guest,
                    'public' => $public,
                );
                $section{'create mask'} = $create_mask if length $create_mask;
                $section{'directory mask'} = $directory_mask if length $directory_mask;
                $section{'write list'} = join(' ', @write_list) if @write_list;
                $section{'read list'} = join(' ', @read_list) if @read_list;

                eval {
                    my $raw = read_file_text($SMB_CONF);
                    my $new_raw = $raw;
                    if (length $original_name) {
                        $new_raw = ini_remove_section($new_raw, $original_name);
                    } else {
                        $new_raw = ini_remove_section($new_raw, $name);
                    }
                    $new_raw = ini_append_section($new_raw, $name, \%section);
                    my $backup = write_file_with_backup($SMB_CONF, $new_raw);

                    if ($in{'restart_after_save'}) {
                        my ($rc) = service_run('smbd', 'restart');
                        if ($rc != 0) {
                            service_run('samba_server', 'restart');
                        }
                    }

                    print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
                    print &ui_print_success(L("SUCCESS_SMB_SHARE_CREATED", $name));
                    $edit_share = $name if length $original_name;
                };
                if ($@) {
                    print &ui_print_error(L("ERR_SMB_CONFIG_SAVE_FAILED", $@));
                }
            }
        }
    }

    my $raw_conf = read_file_text($SMB_CONF);
    my $parsed = parse_ini_sections($raw_conf);

    my @smb_heads = (
        L("COL_SHARE_NAME"),
        L("COL_PATH"),
        L("COL_OPTIONS"),
        L("COL_ACTIONS"),
    );
    my $global_vals = $parsed->{sections}{global}{values} || {};
    my @smb_rows;
    if (@{ $parsed->{shares} }) {
        for my $share (@{ $parsed->{shares} }) {
            my $sec = $parsed->{sections}{ lc($share->{name} || '') }{values} || {};
            my @opt_lines;
            my @opt_map = (
                [ L("COL_COMMENT"),            'comment' ],
                [ L("COL_READONLY"),           'read only' ],
                [ L("COL_BROWSEABLE"),         'browseable', 'browsable' ],
                [ L("COL_GUEST"),              'guest ok' ],
                [ L("ROW_PUBLIC"),             'public' ],
                [ L("ROW_SMB_WRITE_LIST"),     'write list' ],
                [ L("ROW_SMB_READ_LIST"),      'read list' ],
                [ L("ROW_SMB_CREATE_MASK"),    'create mask' ],
                [ L("ROW_SMB_DIRECTORY_MASK"), 'directory mask' ],
            );
            for my $m (@opt_map) {
                my ($label, $key, $alt) = @$m;
                my $val = _smb_effective_value($sec, $global_vals, $key, $alt);
                next unless defined $val && length $val;
                push @opt_lines, &html_escape($label) . ": " . &html_escape($val);
            }
            my $opts = @opt_lines ? join("<br>", @opt_lines) : '-';
            my $actions =
                &ui_form_start("access.cgi", "post") .
                &ui_hidden("action", "smb_shares") .
                &ui_hidden("share_name", $share->{name}) .
                "<button type='submit' name='edit_share' class='button'>" . &html_escape(L("BTN_MODIFY")) . "</button> " .
                "<button type='submit' name='delete_share' class='zfsguru-delete-btn'>" . &html_escape(L("BTN_DELETE")) . "</button>" .
                &ui_form_end();
            push @smb_rows, [
                &html_escape($share->{name}),
                &html_escape($share->{path} || '-'),
                $opts,
                $actions,
            ];
        }
    }
    print &ui_columns_table(\@smb_heads, 100, \@smb_rows, undef, 1, L("TABLE_SMB_SHARES"), L("VALUE_NONE"));

    my $is_modify = 0;
    my %form = (
        original_share_name => '',
        new_share_name => '',
        new_share_path => '',
        new_share_comment => '',
        new_share_readonly => 0,
        new_share_browseable => 1,
        new_share_guest => 0,
        new_share_public => 0,
        new_share_mask_mode => 'none',
        new_share_create_mask => '0644',
        new_share_directory_mask => '0775',
        restart_after_save => 0,
    );
    my @form_write = ();
    my @form_read = ();

    if (length($edit_share) && $edit_share =~ /^[A-Za-z0-9._-]{1,32}$/) {
        my $sec = $parsed->{sections}{ lc($edit_share) }{values} || {};
        if (%$sec) {
            $is_modify = 1;
            $form{original_share_name} = $edit_share;
            $form{new_share_name} = $edit_share;
            $form{new_share_path} = _smb_effective_value($sec, $global_vals, 'path');
            $form{new_share_comment} = _smb_effective_value($sec, $global_vals, 'comment');
            my $ro = _smb_effective_value($sec, $global_vals, 'read only');
            my $br = _smb_effective_value($sec, $global_vals, 'browseable', 'browsable');
            my $go = _smb_effective_value($sec, $global_vals, 'guest ok');
            my $pu = _smb_effective_value($sec, $global_vals, 'public');
            $form{new_share_readonly} = ($ro =~ /^(?:yes|on|true|1)$/i) ? 1 : 0;
            $form{new_share_browseable} = ($br =~ /^(?:yes|on|true|1)$/i) ? 1 : 0;
            $form{new_share_guest} = ($go =~ /^(?:yes|on|true|1)$/i) ? 1 : 0;
            $form{new_share_public} = ($pu =~ /^(?:yes|on|true|1)$/i) ? 1 : 0;

            my $cm = _smb_effective_value($sec, $global_vals, 'create mask');
            my $dm = _smb_effective_value($sec, $global_vals, 'directory mask');
            if ($cm eq '0644' && $dm eq '0775') {
                $form{new_share_mask_mode} = 'preset_644_775';
            } elsif ($cm eq '0755' && $dm eq '0775') {
                $form{new_share_mask_mode} = 'preset_755_775';
            } elsif (length($cm) || length($dm)) {
                $form{new_share_mask_mode} = 'custom';
                $form{new_share_create_mask} = $cm if length $cm;
                $form{new_share_directory_mask} = $dm if length $dm;
            }

            @form_write = smb_split_user_list(_smb_effective_value($sec, $global_vals, 'write list'));
            @form_read = smb_split_user_list(_smb_effective_value($sec, $global_vals, 'read list'));
        }
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_SMB_MODIFY_SHARE"));
    print &ui_form_start("access.cgi", "post");
    print &ui_hidden("action", "smb_shares");
    print &ui_hidden("save_share", 1);
    print &ui_hidden("original_share_name", $form{original_share_name});
    print &ui_table_start(L("TABLE_SMB_PARAMS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($SMB_CONF));
    print &ui_table_row(L("ROW_SHARE_NAME"), &ui_textbox("new_share_name", $form{new_share_name}, 30));
    print &ui_table_row(L("ROW_PATH"), &ui_filebox("new_share_path", $form{new_share_path}, 60, 0, undef, undef, 1));
    print &ui_table_row(L("ROW_COMMENT"), &ui_textbox("new_share_comment", $form{new_share_comment}, 60));
    print &ui_table_row(L("ROW_READONLY"), &ui_checkbox("new_share_readonly", 1, L("OPT_YES"), $form{new_share_readonly}));
    print &ui_table_row(L("ROW_BROWSEABLE"), &ui_checkbox("new_share_browseable", 1, L("OPT_YES"), $form{new_share_browseable}));
    print &ui_table_row(L("ROW_GUEST_OK"), &ui_checkbox("new_share_guest", 1, L("OPT_YES"), $form{new_share_guest}));
    print &ui_table_row(L("ROW_PUBLIC"), &ui_checkbox("new_share_public", 1, L("OPT_YES"), $form{new_share_public}));
    print &ui_table_row(L("ROW_SMB_MASK_MODE"), &ui_select("new_share_mask_mode", $form{new_share_mask_mode}, [
        [ "none", L("OPT_SMB_MASK_NONE") ],
        [ "preset_644_775", L("OPT_SMB_MASK_PRESET_644_775") ],
        [ "preset_755_775", L("OPT_SMB_MASK_PRESET_755_775") ],
        [ "custom", L("OPT_SMB_MASK_CUSTOM") ],
    ]));
    print &ui_table_row(
        L("ROW_SMB_CREATE_MASK"),
        &ui_textbox("new_share_create_mask", $form{new_share_create_mask}, 8) . " <small>" . L("HINT_SMB_CREATE_MASK_EXEC") . "</small>"
    );
    print &ui_table_row(L("ROW_SMB_DIRECTORY_MASK"), &ui_textbox("new_share_directory_mask", $form{new_share_directory_mask}, 8));
    my @write_sel = map { [ $_, $_ ] } @form_write;
    my @read_sel  = map { [ $_, $_ ] } @form_read;
    print &ui_table_row(L("ROW_SMB_WRITE_LIST"),
        @smb_user_opts
            ? &ui_multi_select("new_share_write_list", \@write_sel, \@smb_user_opts, 8, 1, 0, L("LBL_SMB_USERS_AVAILABLE"), L("LBL_SMB_USERS_SELECTED"), 260)
            : &html_escape(L("MSG_SMB_NO_USERS_AVAILABLE")));
    print &ui_table_row(L("ROW_SMB_READ_LIST"),
        @smb_user_opts
            ? &ui_multi_select("new_share_read_list", \@read_sel, \@smb_user_opts, 8, 1, 0, L("LBL_SMB_USERS_AVAILABLE"), L("LBL_SMB_USERS_SELECTED"), 260)
            : &html_escape(L("MSG_SMB_NO_USERS_AVAILABLE")));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), $form{restart_after_save}));
    print &ui_table_end();
    print &ui_form_end([ [ "save_share", ($is_modify ? L("BTN_SAVE_CHANGES") : L("BTN_CREATE_SHARE")) ] ]);
}

sub _smb_effective_value {
    my ($section_vals, $global_vals, $key, $alt) = @_;
    $section_vals = {} unless ref($section_vals) eq 'HASH';
    $global_vals = {} unless ref($global_vals) eq 'HASH';
    $key = lc($key || '');
    $alt = lc($alt || '');

    my @keys = grep { defined $_ && length $_ } ($key, $alt);
    for my $k (@keys) {
        my $v = $section_vals->{$k};
        return $v if defined $v && $v ne '';
    }
    for my $k (@keys) {
        my $v = $global_vals->{$k};
        return $v if defined $v && $v ne '';
    }
    return '';
}

sub smb_global_or_default {
    my ($global_vals, $key, $default, $alt) = @_;
    $global_vals = {} unless ref($global_vals) eq 'HASH';
    $key = lc($key || '');
    $alt = lc($alt || '');
    my @keys = grep { defined $_ && length $_ } ($key, $alt);
    for my $k (@keys) {
        my $v = $global_vals->{$k};
        return $v if defined $v && $v ne '';
    }
    return defined $default ? $default : '';
}

sub action_smb_users {
    print &ui_subheading(L("SUB_SMB_USERS"));
    my $pdbedit = has_command('pdbedit') || '/usr/local/bin/pdbedit';
    my $smbpasswd = has_command('smbpasswd') || '/usr/local/bin/smbpasswd';
    my $pw_cmd = has_command('pw') || '/usr/sbin/pw';

    if (!-x $pdbedit) {
        print &ui_print_error(L("ERR_SMB_USER_TOOL_MISSING", $pdbedit));
        return;
    }

    if ($in{'smb_user_add'}) {
        my $user = $in{'smb_new_user'} || '';
        my $pass = $in{'smb_new_pass'} || '';
        my $pass2 = $in{'smb_new_pass2'} || '';
        if ($user !~ /^[A-Za-z0-9._-]{1,32}$/) {
            print &ui_print_error(L("ERR_SMB_USER_INVALID", $user));
        } elsif (!$in{'confirm_smb_user_add'}) {
            print &ui_print_error(L("ERR_CONFIRM_SMB_USER_ADD_REQUIRED"));
        } elsif (!length($pass) || $pass ne $pass2) {
            print &ui_print_error(L("ERR_SMB_USER_PASSWORD_MISMATCH"));
        } elsif (!-x $smbpasswd) {
            print &ui_print_error(L("ERR_SMB_USER_TOOL_MISSING", $smbpasswd));
        } else {
            eval {
                if ($in{'create_unix_user'}) {
                    my $exists = getpwnam($user) ? 1 : 0;
                    if (!$exists) {
                        my ($rc, $out, $err) = run_cmd($pw_cmd, 'useradd', $user, '-m', '-s', '/usr/sbin/nologin');
                        die($err || $out || "pw useradd failed") if $rc != 0;
                    }
                }
                my ($ok, $err) = smbpasswd_set_password($smbpasswd, $user, $pass);
                die $err unless $ok;
                print &ui_print_success(L("SUCCESS_SMB_USER_ADDED", $user));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SMB_USER_ADD_FAILED", $@));
            }
        }
    }

    if ($in{'smb_user_delete'}) {
        my $user = $in{'smb_user'} || '';
        if ($user !~ /^[A-Za-z0-9._-]{1,32}$/) {
            print &ui_print_error(L("ERR_SMB_USER_INVALID", $user));
        } elsif (!$in{'confirm_smb_user_delete'}) {
            print &ui_print_error(L("ERR_CONFIRM_SMB_USER_DELETE_REQUIRED"));
        } else {
            eval {
                my ($rc, $out, $err) = run_cmd($pdbedit, '-x', $user);
                die($err || $out || "pdbedit delete failed") if $rc != 0;
                print &ui_print_success(L("SUCCESS_SMB_USER_DELETED", $user));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SMB_USER_DELETE_FAILED", $@));
            }
        }
    }

    if ($in{'smb_user_enable'} || $in{'smb_user_disable'}) {
        my $user = $in{'smb_user'} || '';
        my $mode = $in{'smb_user_enable'} ? 'enable' : 'disable';
        if ($user !~ /^[A-Za-z0-9._-]{1,32}$/) {
            print &ui_print_error(L("ERR_SMB_USER_INVALID", $user));
        } elsif (!$in{'confirm_smb_user_toggle'}) {
            print &ui_print_error(L("ERR_CONFIRM_SMB_USER_TOGGLE_REQUIRED"));
        } elsif (!-x $smbpasswd) {
            print &ui_print_error(L("ERR_SMB_USER_TOOL_MISSING", $smbpasswd));
        } else {
            eval {
                my @cmd = ($smbpasswd, ($mode eq 'enable' ? '-e' : '-d'), $user);
                my ($rc, $out, $err) = run_cmd(@cmd);
                die($err || $out || "smbpasswd $mode failed") if $rc != 0;
                print &ui_print_success($mode eq 'enable'
                    ? L("SUCCESS_SMB_USER_ENABLED", $user)
                    : L("SUCCESS_SMB_USER_DISABLED", $user));
            };
            if ($@) {
                print &ui_print_error(L("ERR_SMB_USER_TOGGLE_FAILED", $@));
            }
        }
    }

    my $users = smb_users_info($pdbedit);
    print "<p>" . L("MSG_SMB_USERS_NOTE") . "</p>";

    my @heads = (L("COL_USER"), L("COL_STATUS"), L("COL_FLAGS"), L("COL_ACTIONS"));
    my @data;
    for my $u (@$users) {
        my $name = $u->{name} || next;
        my $flags = $u->{flags} || '';
        my $disabled = ($flags =~ /D/) ? 1 : 0;
        my $status = $disabled ? L("VALUE_DISABLED") : L("VALUE_ENABLED");
        my $status_class = $disabled ? 'zfsguru-status-bad' : 'zfsguru-status-ok';
        my $flags_human = smb_flags_human($flags);

        my $actions =
            &ui_form_start("access.cgi", "post") .
            &ui_hidden("action", "smb_users") .
            &ui_hidden("smb_user", $name) .
            &ui_checkbox("confirm_smb_user_toggle", 1, L("LBL_CONFIRM_SMB_USER_TOGGLE"), 0) . " " .
            ($disabled ? &ui_submit(L("BTN_ENABLE"), "smb_user_enable") : &ui_submit(L("BTN_DISABLE"), "smb_user_disable")) . " " .
            &ui_checkbox("confirm_smb_user_delete", 1, L("LBL_CONFIRM_SMB_USER_DELETE"), 0) . " " .
            "<button type='submit' name='smb_user_delete' class='zfsguru-delete-btn'>" . &html_escape(L("BTN_DELETE")) . "</button>" .
            &ui_form_end();

        push @data, [
            &html_escape($name),
            "<span class='$status_class'>" . &html_escape($status) . "</span>",
            &html_escape($flags_human),
            $actions,
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_SMB_USERS"), L("VALUE_NONE"));

    print &ui_hr();
    print &ui_subheading(L("SUB_SMB_USER_ADD"));
    print &ui_form_start("access.cgi", "post");
    print &ui_hidden("action", "smb_users");
    print &ui_hidden("smb_user_add", 1);
    print &ui_table_start(L("TABLE_SMB_USER_ADD"), "width=100%", 2);
    print &ui_table_row(L("ROW_USER"), &ui_textbox("smb_new_user", "", 30));
    print &ui_table_row(L("ROW_PASSWORD"), &ui_password("smb_new_pass", "", 30));
    print &ui_table_row(L("ROW_PASSWORD_CONFIRM"), &ui_password("smb_new_pass2", "", 30));
    print &ui_table_row(L("ROW_CREATE_UNIX_USER"),
        &ui_checkbox("create_unix_user", 1, L("LBL_CREATE_UNIX_USER"), 0));
    print &ui_table_row(L("ROW_CONFIRM"),
        &ui_checkbox("confirm_smb_user_add", 1, L("LBL_CONFIRM_SMB_USER_ADD"), 0));
    print &ui_table_end();
    print &ui_form_end([ [ "smb_user_add", L("BTN_ADD_USER") ] ]);
}

sub action_smb_settings {
    print &ui_subheading(L("SUB_SMB_SETTINGS"));
    print "<p>" . L("MSG_SMB_SETTINGS_NOTE") . "</p>";

    my %def = (
        'server role' => 'standalone server',
        'read only' => 'no',
        'browseable' => 'yes',
        'guest ok' => 'no',
        'public' => 'no',
        'invalid users' => '',
        'valid users' => '',
        'create mask' => '',
        'write list' => '',
        'read list' => '',
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

    if ($in{'save_smb_settings'}) {
        eval {
            my %set = (
                'workgroup'     => ($in{'smb_workgroup'} // ''),
                'server string' => ($in{'smb_server_string'} // ''),
                'netbios name'  => ($in{'smb_netbios_name'} // ''),
                'security'      => ($in{'smb_security'} // 'user'),
                'map to guest'  => ($in{'smb_map_to_guest'} // 'Never'),
                'guest account' => ($in{'smb_guest_account'} // 'nobody'),
                'log level'     => ($in{'smb_log_level'} // '1'),
                'server role'   => ($in{'smb_server_role'} // $def{'server role'}),
                'interfaces'    => ($in{'smb_interfaces'} // ''),
                'hosts allow'   => ($in{'smb_hosts_allow'} // ''),
                'hosts deny'    => ($in{'smb_hosts_deny'} // ''),
                'read only'     => ($in{'smb_read_only'} // $def{'read only'}),
                'browseable'    => ($in{'smb_browseable'} // $def{'browseable'}),
                'guest ok'      => ($in{'smb_guest_ok'} // $def{'guest ok'}),
                'public'        => ($in{'smb_public'} // $def{'public'}),
                'invalid users' => ($in{'smb_invalid_users'} // $def{'invalid users'}),
                'valid users'   => ($in{'smb_valid_users'} // $def{'valid users'}),
                'create mask'   => ($in{'smb_create_mask'} // $def{'create mask'}),
                'write list'    => ($in{'smb_write_list'} // $def{'write list'}),
                'read list'     => ($in{'smb_read_list'} // $def{'read list'}),
                'directory mask' => ($in{'smb_directory_mask'} // $def{'directory mask'}),
                'force create mode' => ($in{'smb_force_create_mode'} // $def{'force create mode'}),
                'force directory mode' => ($in{'smb_force_directory_mode'} // $def{'force directory mode'}),
                'passdb backend' => ($in{'smb_passdb_backend'} // $def{'passdb backend'}),
                'idmap config * : backend' => ($in{'smb_idmap_backend'} // $def{'idmap config * : backend'}),
                'idmap config * : range' => ($in{'smb_idmap_range'} // $def{'idmap config * : range'}),
                'case sensitive' => ($in{'smb_case_sensitive'} // $def{'case sensitive'}),
                'default case' => ($in{'smb_default_case'} // $def{'default case'}),
                'preserve case' => ($in{'smb_preserve_case'} // $def{'preserve case'}),
                'short preserve case' => ($in{'smb_short_preserve_case'} // $def{'short preserve case'}),
                'ea support' => ($in{'smb_ea_support'} // $def{'ea support'}),
                'vfs objects' => ($in{'smb_vfs_objects'} // $def{'vfs objects'}),
                'nfs4:mode' => ($in{'smb_nfs4_mode'} // $def{'nfs4:mode'}),
                'nfs4:acedup' => ($in{'smb_nfs4_acedup'} // $def{'nfs4:acedup'}),
                'nfs4:chown' => ($in{'smb_nfs4_chown'} // $def{'nfs4:chown'}),
                'map acl inherit' => ($in{'smb_map_acl_inherit'} // $def{'map acl inherit'}),
                'disable netbios' => ($in{'smb_disable_netbios'} // $def{'disable netbios'}),
                'server smb encrypt' => ($in{'smb_server_smb_encrypt'} // $def{'server smb encrypt'}),
                'inherit acls' => ($in{'smb_inherit_acls'} // $def{'inherit acls'}),
                'inherit permissions' => ($in{'smb_inherit_permissions'} // $def{'inherit permissions'}),
                'dos filemode' => ($in{'smb_dos_filemode'} // $def{'dos filemode'}),
                'store dos attributes' => ($in{'smb_store_dos_attributes'} // $def{'store dos attributes'}),
                'acl allow execute always' => ($in{'smb_acl_allow_execute_always'} // $def{'acl allow execute always'}),
                'load printers' => ($in{'smb_load_printers'} // $def{'load printers'}),
                'printing' => ($in{'smb_printing'} // $def{'printing'}),
                'printcap name' => ($in{'smb_printcap_name'} // $def{'printcap name'}),
                'disable spoolss' => ($in{'smb_disable_spoolss'} // $def{'disable spoolss'}),
                'follow symlinks' => ($in{'smb_follow_symlinks'} // $def{'follow symlinks'}),
                'wide links' => ($in{'smb_wide_links'} // $def{'wide links'}),
                'unix extensions' => ($in{'smb_unix_extensions'} // $def{'unix extensions'}),
                'socket options' => ($in{'smb_socket_options'} // $def{'socket options'}),
            );
            for my $k (keys %set) {
                my $v = $set{$k};
                $v =~ s/[\r\n]//g if defined $v;
                $set{$k} = $v;
            }
            die L("ERR_SMB_WORKGROUP_INVALID") if length($set{'workgroup'}) && $set{'workgroup'} !~ /^[A-Za-z0-9._-]{1,32}$/;
            die L("ERR_SMB_SECURITY_INVALID", $set{'security'}) if $set{'security'} !~ /^(user|share|domain|ads)$/;
            die L("ERR_SMB_LOGLEVEL_INVALID", $set{'log level'}) if $set{'log level'} !~ /^\d+$/;

            my $raw = read_file_text($SMB_CONF);
            my $new_raw = ini_set_global_section($raw, \%set);
            my $backup = write_file_with_backup($SMB_CONF, $new_raw);
            if ($in{'restart_after_save'}) {
                my ($rc) = service_run('smbd', 'restart');
                if ($rc != 0) {
                    service_run('samba_server', 'restart');
                }
            }
            print &ui_print_success(L("SUCCESS_CONFIG_SAVED_BACKUP", $backup || '-'));
            print &ui_print_success(L("SUCCESS_SMB_SETTINGS_SAVED"));
        };
        if ($@) {
            print &ui_print_error(L("ERR_SMB_SETTINGS_SAVE_FAILED", $@));
        }
    }

    my $raw_conf = read_file_text($SMB_CONF);
    my $parsed = parse_ini_sections($raw_conf);
    my $global = $parsed->{sections}{global}{values} || {};
    my @yesno = (
        [ 'yes', L("OPT_YES") ],
        [ 'no',  L("OPT_NO") ],
    );

    print &ui_form_start("access.cgi", "post");
    print &ui_hidden("action", "smb_settings");
    print &ui_hidden("save_smb_settings", 1);
    print &ui_table_start(L("TABLE_SMB_SETTINGS"), "width=100%", 2);
    print &ui_table_row(L("ROW_CONFIG_FILE"), &html_escape($SMB_CONF));
    print &ui_table_span("<b>1. General / Identity</b>");
    print &ui_table_row(L("ROW_WORKGROUP"), &ui_textbox("smb_workgroup", ($global->{'workgroup'} || ''), 30));
    print &ui_table_row(L("ROW_SERVER_STRING"), &ui_textbox("smb_server_string", ($global->{'server string'} || ''), 60));
    print &ui_table_row(L("ROW_NETBIOS_NAME"), &ui_textbox("smb_netbios_name", ($global->{'netbios name'} || ''), 30));
    print &ui_table_row("server role", &ui_select("smb_server_role", smb_global_or_default($global, 'server role', $def{'server role'}), [
        [ 'standalone server', 'standalone server' ],
        [ 'member server', 'member server' ],
        [ 'active directory domain controller', 'active directory domain controller' ],
    ]));
    print &ui_table_span("<b>2. Authentication</b>");
    print &ui_table_row(L("ROW_SECURITY_MODE"), &ui_select("smb_security", ($global->{'security'} || 'user'), [
        [ 'user', 'user' ],
        [ 'share', 'share' ],
        [ 'domain', 'domain' ],
        [ 'ads', 'ads' ],
    ]));
    print &ui_table_row(L("ROW_MAP_TO_GUEST"), &ui_select("smb_map_to_guest", ($global->{'map to guest'} || 'Never'), [
        [ 'Never', 'Never' ],
        [ 'Bad User', 'Bad User' ],
        [ 'Bad Password', 'Bad Password' ],
    ]));
    print &ui_table_row(L("ROW_GUEST_ACCOUNT"), &ui_textbox("smb_guest_account", ($global->{'guest account'} || 'nobody'), 30));
    print &ui_table_span("<b>3. Log / Diagnostics</b>");
    print &ui_table_row(L("ROW_LOG_LEVEL"), &ui_textbox("smb_log_level", ($global->{'log level'} || '1'), 8));

    print &ui_table_span("<b>4. Network / Protocol</b>");
    print &ui_table_row(L("ROW_INTERFACES"), &ui_textbox("smb_interfaces", ($global->{'interfaces'} || ''), 60));
    print &ui_table_row(L("ROW_HOSTS_ALLOW"), &ui_textbox("smb_hosts_allow", ($global->{'hosts allow'} || ''), 60));
    print &ui_table_row(L("ROW_HOSTS_DENY"), &ui_textbox("smb_hosts_deny", ($global->{'hosts deny'} || ''), 60));

    print &ui_table_span("<b>5. Access Control</b>");
    print &ui_table_row(L("ROW_READONLY"), &ui_select("smb_read_only", smb_global_or_default($global, 'read only', $def{'read only'}), \@yesno));
    print &ui_table_row(L("ROW_BROWSEABLE"), &ui_select("smb_browseable", smb_global_or_default($global, 'browseable', $def{'browseable'}, 'browsable'), \@yesno));
    print &ui_table_row(L("ROW_GUEST_OK"), &ui_select("smb_guest_ok", smb_global_or_default($global, 'guest ok', $def{'guest ok'}), \@yesno));
    print &ui_table_row(L("ROW_PUBLIC"), &ui_select("smb_public", smb_global_or_default($global, 'public', $def{'public'}), \@yesno));
    print &ui_table_row("invalid users", &ui_textbox("smb_invalid_users", smb_global_or_default($global, 'invalid users', $def{'invalid users'}), 60));
    print &ui_table_row("valid users", &ui_textbox("smb_valid_users", smb_global_or_default($global, 'valid users', $def{'valid users'}), 60));
    print &ui_table_row(L("ROW_SMB_WRITE_LIST"), &ui_textbox("smb_write_list", smb_global_or_default($global, 'write list', $def{'write list'}), 60));
    print &ui_table_row(L("ROW_SMB_READ_LIST"), &ui_textbox("smb_read_list", smb_global_or_default($global, 'read list', $def{'read list'}), 60));

    print &ui_table_span("<b>6. Filesystem / Permissions</b>");
    print &ui_table_row(L("ROW_SMB_CREATE_MASK"), &ui_textbox("smb_create_mask", smb_global_or_default($global, 'create mask', $def{'create mask'}), 12));
    print &ui_table_row(L("ROW_SMB_DIRECTORY_MASK"), &ui_textbox("smb_directory_mask", smb_global_or_default($global, 'directory mask', $def{'directory mask'}), 12));
    print &ui_table_row("force create mode", &ui_textbox("smb_force_create_mode", smb_global_or_default($global, 'force create mode', $def{'force create mode'}), 12));
    print &ui_table_row("force directory mode", &ui_textbox("smb_force_directory_mode", smb_global_or_default($global, 'force directory mode', $def{'force directory mode'}), 12));

    print &ui_table_span("<b>7. Auth / ID Mapping</b>");
    print &ui_table_row("passdb backend", &ui_select("smb_passdb_backend", smb_global_or_default($global, 'passdb backend', $def{'passdb backend'}), [
        [ 'tdbsam', 'tdbsam' ],
        [ 'smbpasswd', 'smbpasswd' ],
        [ 'ldapsam', 'ldapsam' ],
    ]));
    print &ui_table_row("idmap config * : backend", &ui_select("smb_idmap_backend", smb_global_or_default($global, 'idmap config * : backend', $def{'idmap config * : backend'}), [
        [ 'tdb', 'tdb' ],
        [ 'rid', 'rid' ],
        [ 'autorid', 'autorid' ],
        [ 'ldap', 'ldap' ],
    ]));
    print &ui_table_row("idmap config * : range", &ui_textbox("smb_idmap_range", smb_global_or_default($global, 'idmap config * : range', $def{'idmap config * : range'}), 24));

    print &ui_table_span("<b>8. Windows Tune / ACL</b>");
    print &ui_table_row("case sensitive", &ui_select("smb_case_sensitive", smb_global_or_default($global, 'case sensitive', $def{'case sensitive'}), [
        [ 'no', L("OPT_NO") ],
        [ 'yes', L("OPT_YES") ],
        [ 'auto', 'auto' ],
    ]));
    print &ui_table_row("default case", &ui_select("smb_default_case", smb_global_or_default($global, 'default case', $def{'default case'}), [
        [ 'lower', 'lower' ],
        [ 'upper', 'upper' ],
    ]));
    print &ui_table_row("preserve case", &ui_select("smb_preserve_case", smb_global_or_default($global, 'preserve case', $def{'preserve case'}), \@yesno));
    print &ui_table_row("short preserve case", &ui_select("smb_short_preserve_case", smb_global_or_default($global, 'short preserve case', $def{'short preserve case'}), \@yesno));
    print &ui_table_row("ea support", &ui_select("smb_ea_support", smb_global_or_default($global, 'ea support', $def{'ea support'}), \@yesno));
    print &ui_table_row("vfs objects", &ui_select("smb_vfs_objects", smb_global_or_default($global, 'vfs objects', $def{'vfs objects'}), [
        [ 'zfsacl', 'zfsacl' ],
        [ 'acl_xattr', 'acl_xattr' ],
        [ '', '(none)' ],
    ]));
    print &ui_table_row("nfs4:mode", &ui_select("smb_nfs4_mode", smb_global_or_default($global, 'nfs4:mode', $def{'nfs4:mode'}), [
        [ 'simple', 'simple' ],
        [ 'special', 'special' ],
    ]));
    print &ui_table_row("nfs4:acedup", &ui_select("smb_nfs4_acedup", smb_global_or_default($global, 'nfs4:acedup', $def{'nfs4:acedup'}), [
        [ 'merge', 'merge' ],
        [ 'dontcare', 'dontcare' ],
    ]));
    print &ui_table_row("nfs4:chown", &ui_select("smb_nfs4_chown", smb_global_or_default($global, 'nfs4:chown', $def{'nfs4:chown'}), \@yesno));
    print &ui_table_row("map acl inherit", &ui_select("smb_map_acl_inherit", smb_global_or_default($global, 'map acl inherit', $def{'map acl inherit'}), \@yesno));
    print &ui_table_row("disable netbios", &ui_select("smb_disable_netbios", smb_global_or_default($global, 'disable netbios', $def{'disable netbios'}), \@yesno));
    print &ui_table_row("server smb encrypt", &ui_select("smb_server_smb_encrypt", smb_global_or_default($global, 'server smb encrypt', $def{'server smb encrypt'}), [
        [ 'auto', 'auto' ],
        [ 'off', 'off' ],
        [ 'desired', 'desired' ],
        [ 'required', 'required' ],
    ]));
    print &ui_table_row("inherit acls", &ui_select("smb_inherit_acls", smb_global_or_default($global, 'inherit acls', $def{'inherit acls'}), \@yesno));
    print &ui_table_row("inherit permissions", &ui_select("smb_inherit_permissions", smb_global_or_default($global, 'inherit permissions', $def{'inherit permissions'}), \@yesno));
    print &ui_table_row("dos filemode", &ui_select("smb_dos_filemode", smb_global_or_default($global, 'dos filemode', $def{'dos filemode'}), \@yesno));
    print &ui_table_row("store dos attributes", &ui_select("smb_store_dos_attributes", smb_global_or_default($global, 'store dos attributes', $def{'store dos attributes'}), \@yesno));
    print &ui_table_row("acl allow execute always", &ui_select("smb_acl_allow_execute_always", smb_global_or_default($global, 'acl allow execute always', $def{'acl allow execute always'}), \@yesno));

    print &ui_table_span("<b>9. Printing</b>");
    print &ui_table_row("load printers", &ui_select("smb_load_printers", smb_global_or_default($global, 'load printers', $def{'load printers'}), \@yesno));
    print &ui_table_row("printing", &ui_select("smb_printing", smb_global_or_default($global, 'printing', $def{'printing'}), [
        [ 'bsd', 'bsd' ],
        [ 'cups', 'cups' ],
        [ 'sysv', 'sysv' ],
    ]));
    print &ui_table_row("printcap name", &ui_select("smb_printcap_name", smb_global_or_default($global, 'printcap name', $def{'printcap name'}), [
        [ '/dev/null', '/dev/null' ],
        [ '/etc/printcap', '/etc/printcap' ],
    ]));
    print &ui_table_row("disable spoolss", &ui_select("smb_disable_spoolss", smb_global_or_default($global, 'disable spoolss', $def{'disable spoolss'}), \@yesno));
    print &ui_table_row("follow symlinks", &ui_select("smb_follow_symlinks", smb_global_or_default($global, 'follow symlinks', $def{'follow symlinks'}), \@yesno));
    print &ui_table_row("wide links", &ui_select("smb_wide_links", smb_global_or_default($global, 'wide links', $def{'wide links'}), \@yesno));
    print &ui_table_row("unix extensions", &ui_select("smb_unix_extensions", smb_global_or_default($global, 'unix extensions', $def{'unix extensions'}), \@yesno));
    print &ui_table_row("socket options", &ui_textbox("smb_socket_options", smb_global_or_default($global, 'socket options', $def{'socket options'}), 60));

    print &ui_table_span("<b>10. Apply</b>");
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 1));
    print &ui_table_end();
    print &ui_form_end([ [ "save_smb_settings", L("BTN_SAVE_SMB_SETTINGS") ] ]);

    print "<p><a class='button' href='services.cgi?action=smb'>" . L("BTN_OPEN_SERVICES_SMB") . "</a></p>";
}

sub action_nfs_access {
    print &ui_subheading(L("SUB_NFS_ACCESS"));
    print "<p>" . L("MSG_NFS_ACCESS_HELP") . "</p>";

    if ($in{'set_sharenfs'}) {
        my $dataset = $in{'dataset'} || '';
        my $value = $in{'sharenfs_value'};
        if (!is_dataset_name($dataset)) {
            print &ui_print_error(L("ERR_DATASET_NOT_FOUND"));
        } else {
            eval {
                $value = 'on' if $in{'share_on'};
                $value = 'off' if $in{'share_off'};
                $value = '' unless defined $value;
                zfs_set($dataset, 'sharenfs', $value);

                if ($in{'restart_after_save'}) {
                    my ($mrc) = service_run('mountd', 'reload');
                    if ($mrc != 0) {
                        service_run('mountd', 'restart');
                    }
                }
                print &ui_print_success(L("SUCCESS_NFS_SHARE_UPDATED", $dataset));
            };
            if ($@) {
                print &ui_print_error(L("ERR_NFS_CONFIG_SAVE_FAILED", $@));
            }
        }
    }

    my $datasets = zfs_list([qw(name)], '-t', 'filesystem');
    my %sharevals = zfs_get_sharenfs_all($datasets);
    my $default_ds = $in{'dataset'} || '';
    $default_ds = '' unless is_dataset_name($default_ds);

    print &ui_form_start("access.cgi", "post");
    print &ui_hidden("action", "nfs");
    print &ui_hidden("set_sharenfs", 1);
    print &ui_table_start(L("TABLE_NFS_ACCESS_SET"), "width=100%", 2);
    print &ui_table_row(L("ROW_DATASET_NAME"), &ui_select("dataset", $default_ds, [ map { [ $_->{name}, $_->{name} ] } @$datasets ]));
    print &ui_table_row(L("ROW_SHARENFS_VALUE"), &ui_textbox("sharenfs_value", "on", 40));
    print &ui_table_row(L("ROW_RESTART_AFTER_SAVE"), &ui_checkbox("restart_after_save", 1, L("OPT_YES"), 0));
    print &ui_table_end();
    print &ui_form_end([
        [ "share_on", L("BTN_NFS_SHARE_ON") ],
        [ "share_off", L("BTN_NFS_SHARE_OFF") ],
        [ "set_sharenfs", L("BTN_SET_CUSTOM") ],
    ]);

    my @nfs_heads = (
        L("COL_FILESYSTEM"), L("COL_SHARENFS"),
        L("COL_FILESYSTEM"), L("COL_SHARENFS"),
    );
    my @nfs_rows;
    if (@$datasets) {
        for (my $i = 0; $i < @$datasets; $i += 2) {
            my $ds1 = $datasets->[$i];
            my $ds2 = ($i + 1 < @$datasets) ? $datasets->[$i + 1] : undef;

            my $n1 = $ds1 && $ds1->{name} ? $ds1->{name} : '-';
            my $v1 = exists $sharevals{$n1} ? $sharevals{$n1} : '-';
            my $n2 = $ds2 && $ds2->{name} ? $ds2->{name} : '-';
            my $v2 = ($ds2 && exists $sharevals{$n2}) ? $sharevals{$n2} : '-';

            push @nfs_rows, [
                &html_escape($n1),
                &html_escape($v1),
                &html_escape($n2),
                &html_escape($v2),
            ];
        }
    }
    print &ui_columns_table(\@nfs_heads, 100, \@nfs_rows, undef, 1, L("TABLE_NFS_ACCESS_LIST"), L("VALUE_NONE"));
}

sub action_ssh_access {
    print &ui_subheading(L("SUB_SSH_ACCESS"));
    my $host = hostname();
    my $ip = detect_server_ip($host);
    my $port = parse_sshd_port(read_file_text($SSHD_CONF)) || '22';

    print &ui_table_start(L("TABLE_SSH_ACCESS"), "width=100%", 2);
    print &ui_table_row(L("ROW_HOSTNAME"), &html_escape($host));
    print &ui_table_row(L("ROW_SSH_PORT"), &html_escape($port));
    print &ui_table_row(L("ROW_SERVER_IP"), &html_escape($ip || L("VALUE_UNKNOWN")));
    print &ui_table_end();

    print "<p><a class='button' href='services.cgi?action=ssh'>" . L("BTN_OPEN_SERVICES_SSH") . "</a></p>";
}

sub detect_server_ip {
    my ($host) = @_;

    my $ip = $ENV{'SERVER_ADDR'} || $ENV{'LOCAL_ADDR'} || '';
    return $ip if defined($ip) && $ip =~ /^\d{1,3}(?:\.\d{1,3}){3}$/ && $ip !~ /^127\./;

    my $http_host = $ENV{'HTTP_HOST'} || '';
    if ($http_host =~ /^(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?$/ && $1 !~ /^127\./) {
        return $1;
    }

    my $ifconfig = $zfsguru_lib::IFCONFIG || '/sbin/ifconfig';
    my ($rc, $out, $err) = run_cmd($ifconfig, '-a');
    if ($rc == 0 && $out) {
        for my $line (split /\n/, $out) {
            next if $line =~ /\binet6\b/;
            if ($line =~ /^\s*inet\s+(\d{1,3}(?:\.\d{1,3}){3})\b/) {
                my $cand = $1;
                next if $cand =~ /^127\./;
                next if $cand eq '0.0.0.0';
                return $cand;
            }
        }
    }

    return '';
}

sub action_iscsi_access {
    print &ui_subheading(L("SUB_ISCSI_CONFIG"));
    print "<p>" . L("MSG_ISCSI_ACCESS_NOTE") . "</p>";

    my $targets = parse_ctl_targets(read_file_text($CTL_CONF));
    my ($ctld_state, $ctld_detail) = access_service_state('ctld');
    my $ctld_status =
        $ctld_state eq 'running' ? "<span class='zfsguru-status-ok'>" . L("VALUE_RUNNING") . "</span>" :
        $ctld_state eq 'stopped' ? "<span class='zfsguru-status-bad'>" . L("VALUE_STOPPED") . "</span>" :
                                   "<span class='zfsguru-status-unknown'>" . L("VALUE_UNKNOWN") . "</span>";

    print &ui_table_start("iSCSI Service Status", "width=100%", 2);
    print &ui_table_row("ctld", $ctld_status);
    print &ui_table_row("Details", &html_escape($ctld_detail || '-'));
    print &ui_table_end();

    my %uniq_backend;
    for my $t (@$targets) {
        my $d = $t->{device} || '';
        $uniq_backend{$d} = 1 if length $d;
    }
    print &ui_table_start("iSCSI Summary", "width=100%", 2);
    print &ui_table_row("Targets defined", scalar(@$targets));
    print &ui_table_row("Unique backends", scalar(keys %uniq_backend));
    print &ui_table_row("Config file", &html_escape($CTL_CONF));
    print &ui_table_end();

    print &ui_table_start(L("TABLE_ISCSI_TARGETS"), "width=100%", 2, [
        L("COL_TARGET_NAME"), L("COL_DEVICE"), L("COL_LUN")
    ]);
    if (@$targets) {
        for my $t (@$targets) {
            print &ui_table_row(
                &html_escape($t->{name}),
                &html_escape($t->{device} || '-'),
                &html_escape($t->{lun} || '0')
            );
        }
    } else {
        print &ui_table_row("-", "-", "-");
    }
    print &ui_table_end();

    print "<p><a class='button' href='services.cgi?action=iscsi'>" . L("BTN_OPEN_SERVICES_ISCSI") . "</a></p>";
}

sub access_service_state {
    my ($service_name) = @_;
    return ('unknown', '') unless defined $service_name && length $service_name;
    my ($rc, $out, $err) = service_run($service_name, 'status');
    my $txt = join("\n", grep { defined $_ && length $_ } ($out, $err));
    my $lc = lc($txt || '');

    my $state = 'unknown';
    if ($rc == 0 || $lc =~ /\bis running\b|running as pid|active\s*\(running\)/) {
        $state = 'running';
    } elsif ($lc =~ /not running|isn't running|is not running|stopped|not started|inactive|does not exist|not found|unknown service/) {
        $state = 'stopped';
    }

    my $first = '';
    for my $line (split /\n/, ($txt || '')) {
        $line =~ s/^\s+|\s+$//g;
        next unless length $line;
        $first = $line;
        last;
    }
    return ($state, $first);
}

sub smbpasswd_set_password {
    my ($cmd, $user, $pass) = @_;
    return (0, "missing smbpasswd command") unless defined $cmd && -x $cmd;
    return (0, "invalid user") unless defined $user && $user =~ /^[A-Za-z0-9._-]{1,32}$/;

    my $err = gensym;
    my ($in_fh, $out_fh);
    my $pid = eval { open3($in_fh, $out_fh, $err, $cmd, '-a', '-s', $user) };
    if (!$pid) {
        return (0, $@ || "open3 failed");
    }

    print $in_fh $pass . "\n" . $pass . "\n";
    close($in_fh);
    my $stdout = do { local $/ = undef; <$out_fh> };
    my $stderr = do { local $/ = undef; <$err> };
    close($out_fh);
    close($err);
    waitpid($pid, 0);
    my $rc = $? >> 8;
    return ($rc == 0, $stderr || $stdout || "smbpasswd failed");
}

sub smb_users_info {
    my ($pdbedit) = @_;
    my @users;
    my %flags;

    if (defined $pdbedit && -x $pdbedit) {
        my ($vrc, $vout, $verr) = run_cmd($pdbedit, '-L', '-v');
        if ($vrc == 0 && $vout) {
            my $cur = '';
            for my $line (split /\n/, $vout) {
                if ($line =~ /^\s*Unix username:\s*(\S+)/i) {
                    $cur = $1;
                    next;
                }
                if ($cur && $line =~ /^\s*Account Flags:\s*(\[[^\]]*\])/i) {
                    $flags{$cur} = $1;
                    next;
                }
            }
        }

        my ($rc, $out, $err) = run_cmd($pdbedit, '-L');
        if ($rc == 0 && $out) {
            for my $line (split /\n/, $out) {
                my ($name) = split /:/, $line, 2;
                next unless defined $name && length $name;
                push @users, { name => $name, flags => ($flags{$name} || '') };
            }
        }
    }

    @users = sort { lc($a->{name}) cmp lc($b->{name}) } @users;
    return \@users;
}

sub smb_flags_human {
    my ($raw) = @_;
    $raw = '' unless defined $raw;
    my $flags = $raw;
    $flags =~ s/[\[\]\s]//g;
    return '-' unless length $flags;

    my @desc;
    push @desc, 'User account' if $flags =~ /U/;
    push @desc, 'Disabled' if $flags =~ /D/;
    push @desc, 'No password required' if $flags =~ /N/;
    push @desc, 'Password does not expire' if $flags =~ /X/;
    push @desc, 'Auto-locked' if $flags =~ /L/;
    push @desc, 'Workstation trust account' if $flags =~ /W/;
    push @desc, 'Server trust account' if $flags =~ /S/;

    my %known = map { $_ => 1 } qw(U D N X L W S);
    my @unknown = grep { !$known{$_} } split //, $flags;
    push @desc, 'Other: ' . join('', @unknown) if @unknown;

    return "[$flags] - " . (@desc ? join(', ', @desc) : 'Unknown');
}

sub parse_multi_select_values {
    my ($raw) = @_;
    return () unless defined $raw && length $raw;
    my @vals = split /\n/, $raw;
    my %seen;
    my @out;
    for my $v (@vals) {
        next unless defined $v;
        $v =~ s/^\s+|\s+$//g;
        next unless $v =~ /^[A-Za-z0-9._-]{1,32}$/;
        next if $seen{$v}++;
        push @out, $v;
    }
    return @out;
}

sub normalize_smb_mask {
    my ($raw) = @_;
    $raw = '' unless defined $raw;
    $raw =~ s/^\s+|\s+$//g;
    return '' unless $raw =~ /^(?:0?[0-7]{3}|[0-7]{4})$/;
    $raw =~ s/^0?([0-7]{3})$/0$1/;
    return $raw;
}

sub smb_split_user_list {
    my ($raw) = @_;
    $raw = '' unless defined $raw;
    my @parts = split(/[,\s]+/, $raw);
    my %seen;
    my @out;
    for my $p (@parts) {
        next unless defined $p && $p =~ /^[A-Za-z0-9._-]{1,32}$/;
        next if $seen{$p}++;
        push @out, $p;
    }
    return @out;
}

sub ini_set_global_section {
    my ($raw, $values) = @_;
    $raw = '' unless defined $raw;
    $values = {} unless ref($values) eq 'HASH';

    my $rest = ini_remove_section($raw, 'global');
    my @lines;
    push @lines, '[global]';
    for my $k (sort keys %$values) {
        my $v = $values->{$k};
        next unless defined $v;
        $v =~ s/[\r\n]//g;
        next unless length $v;
        push @lines, "\t$k = $v";
    }
    push @lines, '';
    my $global = join("\n", @lines);
    my $new_raw = $global . ($rest || '');
    $new_raw .= "\n" if $new_raw !~ /\n\z/;
    return $new_raw;
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
            read_only => $vals->{'read only'} || '',
            browseable => $vals->{'browseable'} || $vals->{'browsable'} || '',
            guest_ok => $vals->{'guest ok'} || '',
        };
    }

    return {
        sections => \%sections,
        order    => \@order,
        shares   => \@shares,
    };
}

sub ini_remove_section {
    my ($raw, $section) = @_;
    return $raw unless defined $section && length $section;
    my @lines = split /\n/, ($raw || ''), -1;
    my ($start, $end);
    for my $i (0 .. $#lines) {
        next unless $lines[$i] =~ /^\s*\[\s*\Q$section\E\s*\]\s*$/i;
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
    return $raw unless defined $start;
    splice @lines, $start, ($end - $start + 1);
    my $new_raw = join("\n", @lines);
    $new_raw .= "\n" if $new_raw !~ /\n\z/;
    return $new_raw;
}

sub ini_append_section {
    my ($raw, $section, $values) = @_;
    my $new_raw = $raw || '';
    $new_raw .= "\n" if length($new_raw) && $new_raw !~ /\n\z/;
    $new_raw .= "[$section]\n";
    for my $k (sort keys %$values) {
        my $v = $values->{$k};
        next unless defined $v;
        $new_raw .= "\t$k = $v\n";
    }
    $new_raw .= "\n";
    return $new_raw;
}

sub parse_sshd_port {
    my ($raw) = @_;
    for my $line (split /\n/, ($raw || '')) {
        next if $line =~ /^\s*#/;
        if ($line =~ /^\s*Port\s+(\d+)/i) {
            return $1;
        }
    }
    return undef;
}

sub zfs_get_sharenfs_all {
    my ($datasets) = @_;
    my %vals;
    if (ref($datasets) eq 'ARRAY') {
        for my $ds (@$datasets) {
            next unless $ds->{name};
            my $rows = zfs_get($ds->{name}, 'sharenfs');
            if (ref($rows) eq 'HASH') {
                $vals{$ds->{name}} = defined $rows->{sharenfs} && length $rows->{sharenfs}
                    ? $rows->{sharenfs}
                    : '-';
            } elsif (ref($rows) eq 'ARRAY' && @$rows && ref($rows->[0]) eq 'HASH') {
                $vals{$ds->{name}} = defined $rows->[0]{value} && length $rows->[0]{value}
                    ? $rows->[0]{value}
                    : '-';
            } else {
                $vals{$ds->{name}} = '-';
            }
        }
        return %vals;
    }
    return %vals;
}

1;
