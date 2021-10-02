#!/usr/bin/perl

use File::HomeDir;
use File::Copy;
use CGI qw/:standard/;
use Config::Simple;
use HTML::Entities;
use String::Escape qw( unquotemeta );
use warnings;
no strict "refs"; # we need it for template system
use LoxBerry::System;

my  $home = File::HomeDir->my_home;
my  $lang;
my  $installfolder;
my  $cfg;
my  $conf;
our $psubfolder;
our $template_title;
our $namef;
our $value;
our %query;
our $cache;
our $helptext;
our $language;	
our $select_language;
our $debug;
our $select_debug;
our $do;
our $zisternestatus;
our $miniserver;
our $select_ms;
our $savedata;
our $echo;
our $trigger;
our $abfrage;
our $max_abstand;

# Read Settings
$cfg             = new Config::Simple("$lbsconfigdir/general.cfg");
$installfolder   = $cfg->param("BASE.INSTALLFOLDER");
$lang            = $cfg->param("BASE.LANG");

print "Content-Type: text/html\n\n";

# Parse URL
foreach (split(/&/,$ENV{"QUERY_STRING"}))
{
  ($namef,$value) = split(/=/,$_,2);
  $namef =~ tr/+/ /;
  $namef =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
  $value =~ tr/+/ /;
  $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
  $query{$namef} = $value;
}

# Set parameters coming in - GET over POST
if ( !$query{'miniserver'} ) { if ( param('miniserver') ) { $miniserver = quotemeta(param('miniserver')); } else { $miniserver = $miniserver;  } } else { $miniserver = quotemeta($query{'miniserver'}); }
if ( !$query{'debug'} ) { if ( param('debug') ) { $debug = quotemeta(param('debug')); } else { $debug = "0";  } } else { $debug = quotemeta($query{'debug'}); }
if ( !$query{'echo'} ) { if ( param('echo') ) { $echo = quotemeta(param('echo')); } else { $echo = $echo;  } } else { $echo = quotemeta($query{'echo'}); }
if ( !$query{'trigger'} ) { if ( param('trigger') ) { $trigger = quotemeta(param('trigger')); } else { $trigger = $trigger;  } } else { $trigger = quotemeta($query{'trigger'}); }
if ( !$query{'abfrage'} ) { if ( param('abfrage') ) { $abfrage = quotemeta(param('abfrage')); } else { $abfrage = "60";  } } else { $abfrage = quotemeta($query{'abfrage'}); }
if ( !$query{'max_abstand'} ) { if ( param('max_abstand') ) { $max_abstand = quotemeta(param('max_abstand')); } else { $max_abstand = "500";  } } else { $max_abstand = quotemeta($query{'max_abstand'}); }

# Figure out in which subfolder we are installed
$psubfolder = abs_path($0);
$psubfolder =~ s/(.*)\/(.*)\/(.*)$/$2/g;

# Save settings to config file
if (param('savedata')) {
	$conf = new Config::Simple("$lbpconfigdir/zisterne.cfg");
	if ($debug ne 1) { $debug = 0 }
	$conf->param('MINISERVER', unquotemeta("MINISERVER$miniserver"));	
	$conf->param('DEBUG', unquotemeta($debug));		
    $conf->param('ECHO', unquotemeta($echo));	
    $conf->param('TRIGGER', unquotemeta($trigger));	
    $conf->param('ABFRAGE', unquotemeta($abfrage));	
    $conf->param('MAX_ABSTAND', unquotemeta($max_abstand));	
    
	$conf->save();
	system ("$installfolder/system/daemons/plugins/$psubfolder restart");
}

# Parse config file
$conf = new Config::Simple("$lbpconfigdir/zisterne.cfg");
$miniserver = encode_entities($conf->param('MINISERVER'));
$debug = encode_entities($conf->param('DEBUG'));
$echo = encode_entities($conf->param('ECHO'));
$trigger = encode_entities($conf->param('TRIGGER'));
$abfrage = encode_entities($conf->param('ABFRAGE'));
$max_abstand = encode_entities($conf->param('MAX_ABSTAND'));

# Set Enabled / Disabled switch
#

if ($debug eq "1") {
	$select_debug = '<option value="0">off</option><option value="1" selected>on</option>';
} else {
	$select_debug = '<option value="0" selected>off</option><option value="1">on</option>';
}


# ---------------------------------------
# Fill Miniserver selection dropdown
# ---------------------------------------
for (my $i = 1; $i <= $cfg->param('BASE.MINISERVERS');$i++) {
	if ("MINISERVER$i" eq $miniserver) {
		$select_ms .= '<option selected value="'.$i.'">'.$cfg->param("MINISERVER$i.NAME")."</option>\n";
	} else {
		$select_ms .= '<option value="'.$i.'">'.$cfg->param("MINISERVER$i.NAME")."</option>\n";
	}
}


# ---------------------------------------
# Start Stop Service
# ---------------------------------------
# Should Zisterne-Wasserstand Server be started

if ( param('do') ) { 
	$do = quotemeta( param('do') ); 
	if ( $do eq "start") {
		system ("$installfolder/system/daemons/plugins/$psubfolder start");
	}
	if ( $do eq "stop") {
		system ("$installfolder/system/daemons/plugins/$psubfolder stop");
	}
	if ( $do eq "restart") {
		system ("$installfolder/system/daemons/plugins/$psubfolder restart");
	}
}

# Title
$template_title = "Zisterne-Wasserstand";
$zisternestatus = qx($installfolder/system/daemons/plugins/$psubfolder status);

# Create help page
$helptext = "<b>Hilfe</b><br>Wenn ihr Hilfe beim Einrichten benĂ¶tigt findet ihr diese im LoxWiki.";
$helptext = $helptext . "<br><a href='https://www.loxwiki.eu/display/LOXBERRY/Midea2Lox' target='_blank'>LoxWiki - Midea2Lox</a>";
$helptext = $helptext . "<br><br><b>Debug/Log</b><br>Um Debug zu starten, den Schalter auf on stellen und speichern.<br>Die Log-Datei kann hier eingesehen werden. ";
$helptext = $helptext . "<a href='/admin/system/tools/logfile.cgi?logfile=plugins/$psubfolder/midea2lox.log&header=html&format=template&only=once' target='_blank'>Log-File - Midea2Lox</a>";
$helptext = $helptext . "<br><br><b>Achtung!</b> Wenn Debug aktiv ist werden sehr viele Daten ins Log geschrieben. Bitte nur bei Problemen nutzen.";


# Currently only german is supported - so overwrite user language settings:
#$lang = "de";

# Load header and replace HTML Markup <!--$VARNAME--> with perl variable $VARNAME
open(F,"$lbstemplatedir/$lang/header.html") || die "Missing template system/$lang/header.html";
  while (<F>) {
    $_ =~ s/<!--\$(.*?)-->/${$1}/g;
    print $_;
  }
close(F);

# Load content from template
open(F,"$lbptemplatedir/$lang/content.html") || die "Missing template $lang/content.html";
  while (<F>) {
    $_ =~ s/<!--\$(.*?)-->/${$1}/g;
    print $_;
  }
close(F);

# Load footer and replace HTML Markup <!--$VARNAME--> with perl variable $VARNAME
open(F,"$lbstemplatedir/$lang/footer.html") || die "Missing template system/$lang/header.html";
  while (<F>) {
    $_ =~ s/<!--\$(.*?)-->/${$1}/g;
    print $_;
  }
close(F);

exit;
