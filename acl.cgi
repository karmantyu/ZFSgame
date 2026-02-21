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

zfsguru_page_header(title_key => "TITLE_ACL");

eval { acl_require_feature('acl'); };
if ($@) {
    print &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'acl'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'view';
my $xnav_q = '';
my $xnav_h = '';
if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
    my $xv = $in{'xnavigation'};
    $xnav_q = "&xnavigation=$xv";
    $xnav_h = &ui_hidden("xnavigation", $xv);
}

if ($action eq 'view') {
    &action_view();
} elsif ($action eq 'edit') {
    &action_edit();
}

my $back_url = 'index.cgi';
if ($action ne 'view') {
    $back_url = 'acl.cgi?action=view';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_view {
    if ($in{'delete_user'}) {
        my $del_user = $in{'del_user'} || '';
        $del_user =~ s/^\s+|\s+$//g;
        if ($del_user !~ /^[A-Za-z0-9_.\-]+$/) {
            print &ui_print_error(L("ERR_ACL_INVALID_USER"));
        } elsif (!$in{'confirm_acl_user_delete'}) {
            print &ui_print_error(L("LBL_CONFIRM_ACL_USER_DELETE"));
        } else {
            eval { acl_delete_user_features($del_user); };
            if ($@) {
                print &ui_print_error(L("ERR_ACL_DELETE_FAILED", $@));
            } else {
                print &ui_print_success(L("SUCCESS_ACL_USER_DELETED", $del_user));
            }
        }
    }

    if ($in{'add_user'}) {
        my $new_user = $in{'new_user'} || '';
        $new_user =~ s/^\s+|\s+$//g;
        if ($new_user !~ /^[A-Za-z0-9_.\-]+$/) {
            print &ui_print_error(L("ERR_ACL_INVALID_USER"));
        } else {
            my $level = $in{'new_level'} || 'Basic';
            my $features = acl_ui_level_to_features($level);
            eval { acl_write_user_features($new_user, $features); };
            if ($@) {
                print &ui_print_error(L("ERR_ACL_SAVE_FAILED", $@));
            } else {
                print &ui_print_success(L("SUCCESS_ACL_USER_ADDED", $new_user));
            }
        }
    }

    print &ui_subheading(L("SUB_ACL_MODULE_CONTROL"));
    print "<p>" . L("MSG_ACL_PAGE_INTRO") . "</p>";
    print "<h3>" . L("HDR_ACCESS_LEVELS") . "</h3>";
    print "<ul>";
    print "<li><b>" . L("ACL_LEVEL_FULL") . ":</b> " . L("ACL_LEVEL_FULL_DESC") . "</li>";
    print "<li><b>" . L("ACL_LEVEL_ADVANCED") . ":</b> " . L("ACL_LEVEL_ADVANCED_DESC") . "</li>";
    print "<li><b>" . L("ACL_LEVEL_BASIC") . ":</b> " . L("ACL_LEVEL_BASIC_DESC") . "</li>";
    print "<li><b>" . L("ACL_LEVEL_NONE") . ":</b> " . L("ACL_LEVEL_NONE_DESC") . "</li>";
    print "</ul>";
    print "<h3>" . L("HDR_MODULE_FEATURES") . "</h3>";
    print "<p>" . L("MSG_ACL_USERS_WITH_ACCESS") . "</p>";
    my $acl = acl_read();
    my %all_users;
    for my $u (@{ webmin_usernames() }) {
        $all_users{$u} = 1 if defined $u && $u ne '';
    }
    for my $u (keys %{ $acl->{users} || {} }) {
        $all_users{$u} = 1;
    }
    $all_users{'root'} = 1;

    my @heads = (
        L("COL_USER_GROUP"),
        L("COL_ACCESS_LEVEL"),
        L("COL_FEATURES"),
        L("COL_ACTIONS"),
    );
    my @rows;
    for my $user (sort keys %all_users) {
        my $has_explicit = exists $acl->{users}{$user} ? 1 : 0;
        my $features_ref = $has_explicit
            ? ($acl->{users}{$user} || [])
            : acl_get_user_features($user);
        my $features = @$features_ref ? join(", ", @$features_ref) : L("VALUE_NONE");
        my $level_text = acl_ui_features_to_level($features_ref);
        my $edit = "<a class='button' href='acl.cgi?action=edit&user=" . &url_encode($user) . $xnav_q . "'>" . L("BTN_EDIT") . "</a>";
        my $del = "";
        if ($has_explicit) {
            $del =
                &ui_form_start("acl.cgi", "post", "style='display:inline-block; margin-left:6px;'") .
                &ui_hidden("action", "view") .
                ($xnav_h ? $xnav_h : '') .
                &ui_hidden("del_user", $user) .
                &ui_checkbox("confirm_acl_user_delete", 1, L("LBL_CONFIRM_ACL_USER_DELETE"), 0) . " " .
                "<button type='submit' name='delete_user' class='zfsguru-delete-btn'>" . &html_escape(L("BTN_DELETE")) . "</button>" .
                &ui_form_end();
        }
        push @rows, [
            &html_escape($user),
            &html_escape($level_text),
            &html_escape($features),
            $edit . $del,
        ];
    }

    print &ui_columns_table(\@heads, 100, \@rows, undef, 1, L("TABLE_ACCESS_CONTROL"), L("VALUE_NONE"));
    
    print &ui_hr();
    print &ui_form_start("acl.cgi", "post");
    print &ui_hidden("action", "view");
    print $xnav_h if $xnav_h;
    print &ui_subheading(L("SUB_ADD_NEW_USER_ACCESS"));
    print &ui_table_start(L("TABLE_GRANT_ACCESS"), "width=100%", 2);
    print &ui_table_row(L("ROW_WEBMIN_USER"), &ui_textbox("new_user", "", 30));
    print &ui_table_row(L("ROW_ACCESS_LEVEL"), &ui_select("new_level", "Basic", [
        [ "None", L("ACL_LEVEL_NONE_DESC") ],
        [ "Basic", L("ACL_LEVEL_BASIC_DESC") ],
        [ "Advanced", L("ACL_LEVEL_ADVANCED_DESC") ],
        [ "Full", L("ACL_LEVEL_FULL_DESC") ],
    ]));
    print &ui_table_end();
    print &ui_form_end([ [ "add_user", L("BTN_GRANT_ACCESS") ] ]);
}

sub action_edit {
    my $user = $in{'user'};
    if (!$user || $user !~ /^[A-Za-z0-9_.\-]+$/) {
        print &ui_print_error(L("ERR_ACL_INVALID_USER"));
        return;
    }

    if ($in{'cancel'}) {
        &redirect("acl.cgi?action=view$xnav_q");
        return;
    }

    my $feature_catalog = acl_ui_feature_catalog();
    if ($in{'save_acl'}) {
        my @selected;
        for my $feat (@$feature_catalog) {
            my $id = $feat->[0];
            push @selected, $id if $in{"feat_$id"};
        }
        eval { acl_write_user_features($user, \@selected); };
        if ($@) {
            print &ui_print_error(L("ERR_ACL_SAVE_FAILED", $@));
        } else {
            print &ui_print_success(L("SUCCESS_ACL_SAVED", $user));
        }
    }
    my $selected_features = acl_get_user_features($user);
    my %selected = map { $_ => 1 } @$selected_features;
    
    print &ui_subheading(L("SUB_EDIT_ACCESS", $user));
    
    print &ui_form_start("acl.cgi", "post");
    print &ui_hidden("action", "edit");
    print &ui_hidden("user", $user);
    print $xnav_h if $xnav_h;
    
    print &ui_table_start(L("TABLE_USER_PERMISSIONS"), "width=100%", 2);
    
    for my $feat (@$feature_catalog) {
        my $feat_id = $feat->[0];
        my $feat_name = $feat->[1];
        print &ui_table_row("", &ui_checkbox("feat_$feat_id", 1, $feat_name, $selected{$feat_id} ? 1 : 0));
    }
    
    print &ui_table_end();
    
    print &ui_form_end([
        [ "save_acl", L("BTN_SAVE_CHANGES") ],
        [ "cancel", L("BTN_CANCEL") ],
    ]);
}

sub acl_ui_feature_catalog {
    my $acl = acl_read();
    my %label = (
        overview  => L("FEAT_DASHBOARD_OVERVIEW"),
        pools     => L("FEAT_POOL_MANAGEMENT"),
        datasets  => L("FEAT_DATASET_MANAGEMENT"),
        snapshots => L("FEAT_SNAPSHOT_MANAGEMENT"),
        disks     => L("FEAT_DISK_MANAGEMENT"),
        services  => L("FEAT_SERVICES_MANAGEMENT"),
        access    => L("FEAT_ACCESS_MANAGEMENT"),
        access_smb   => L("FEAT_ACCESS_SMB"),
        access_nfs   => L("FEAT_ACCESS_NFS"),
        access_ssh   => L("FEAT_ACCESS_SSH"),
        access_iscsi => L("FEAT_ACCESS_ISCSI"),
        network   => L("FEAT_NETWORK_MANAGEMENT"),
        system    => L("FEAT_SYSTEM_MANAGEMENT"),
        status    => L("FEAT_SYSTEM_STATUS_LOGS"),
        acl       => L("FEAT_ACL_MANAGEMENT"),
    );

    my @ordered = qw(overview pools datasets snapshots disks services access access_smb access_nfs access_ssh access_iscsi network system status acl);
    my @out;
    for my $id (@ordered) {
        my $desc = exists $label{$id} ? $label{$id} : ($acl->{features}{$id} || $id);
        push @out, [ $id, $desc ];
    }
    return \@out;
}

sub acl_ui_level_to_features {
    my ($level) = @_;
    if ($level eq 'None') {
        return [];
    } elsif ($level eq 'Basic') {
        return [qw(overview status)];
    } elsif ($level eq 'Advanced') {
        return [qw(overview pools datasets snapshots disks services access access_smb access_nfs access_ssh access_iscsi network system status)];
    }
    return [qw(overview pools datasets snapshots disks services access access_smb access_nfs access_ssh access_iscsi network system status acl)];
}

sub acl_ui_features_to_level {
    my ($features_ref) = @_;
    my %f = map { $_ => 1 } @{ $features_ref || [] };
    my $count = scalar(keys %f);
    return L("ACL_LEVEL_NONE") if $count == 0;
    if ($f{acl}) {
        return L("ACL_LEVEL_FULL");
    }
    if ($f{pools} || $f{datasets} || $f{services} || $f{access} || $f{access_smb} || $f{access_nfs} || $f{access_ssh} || $f{access_iscsi} || $f{disks} || $f{network} || $f{system}) {
        return L("ACL_LEVEL_ADVANCED");
    }
    if ($f{overview} || $f{status}) {
        return L("ACL_LEVEL_BASIC");
    }
    return L("ACL_LEVEL_ADVANCED");
}

sub webmin_usernames {
    my %miniserv;
    eval { get_miniserv_config(\%miniserv); };
    my %users;

    my $userfile = $miniserv{'userfile'} || '';
    if (!$@ && $userfile && -r $userfile) {
        my $raw = read_file_contents($userfile);
        if (defined $raw && length $raw) {
            for my $line (split /\n/, $raw) {
                $line =~ s/\r$//;
                next if $line =~ /^\s*#/;
                next unless $line =~ /^([A-Za-z0-9_.\-]+):/;
                $users{$1} = 1;
            }
        }
    }

    my $acl = acl_read();
    for my $u (keys %{ $acl->{users} || {} }) {
        $users{$u} = 1 if defined $u && $u ne '';
    }
    $users{'root'} = 1;

    my @users = sort keys %users;
    return \@users;
}

sub acl_delete_user_features {
    my ($user) = @_;
    die "Invalid user" unless defined $user && $user =~ /^[A-Za-z0-9_.\-]+$/;

    my $path = "$Bin/acl.txt";
    my $raw = read_file_text($path);
    my @lines = length($raw) ? split(/\n/, $raw, -1) : ();
    my $key = "user_$user";
    my $found = 0;
    my @out;
    for my $ln (@lines) {
        if ($ln =~ /^\s*\Q$key\E\s*=/) {
            $found = 1;
            next;
        }
        push @out, $ln;
    }
    return 1 unless $found;
    my $new_raw = join("\n", @out);
    $new_raw .= "\n" if $new_raw !~ /\n\z/;
    write_file_with_backup($path, $new_raw);
    return 1;
}

1;
