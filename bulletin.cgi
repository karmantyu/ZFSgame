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

zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => "TITLE_BULLETIN");

eval { acl_require_feature('overview'); };
if ($@) {
    print &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'overview'));
    zfsguru_page_footer();
    exit 0;
}

print &ui_subheading(L("SUB_BULLETIN"));
print "<p>" . L("MSG_BULLETIN_NONE") . "</p>";

zfsguru_page_footer();

