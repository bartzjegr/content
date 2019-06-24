#!/usr/bin/env python2
from __future__ import print_function

import logging
import re

from ssg.constants import OSCAP_PROFILE
from ssg_test_suite.common import send_scripts
from ssg_test_suite import rule
from ssg_test_suite import xml_operations
from ssg_test_suite import test_env
import data


class CombinedChecker(rule.RuleChecker):
    """
    Rule checks generally work like this -
    for every profile that supports that rule:

    - Alter the system.
    - Run the scan, check that the result meets expectations.
      If the test scenario passed as requested, return True,
      if it failed or passed unexpectedly, return False.

    The following sequence applies if the initial scan
    has failed as expected:

    - If there are no remediations, return True.
    - Run remediation, return False if it failed.
    - Return result of the final scan of remediated system.
    """
    def __init__(self, test_env):
        super(CombinedChecker, self).__init__(test_env)
        self._matching_rule_found = False

        self.results = list()
        self._current_result = None

    def _parse_parameters(self, script):
        """Parse parameters from script header"""
        params = {'templates': [],
                  'platform': ['multi_platform_all'],
                  'remediation': ['all']}
        with open(script, 'r') as script_file:
            script_content = script_file.read()
            for parameter in params:
                found = re.search('^# {0} = ([ ,_\.\-\w]*)$'.format(parameter),
                                  script_content,
                                  re.MULTILINE)
                if found is None:
                    continue
                splitted = found.group(1).split(',')
                params[parameter] = [value.strip() for value in splitted]

            # Override any metadata in test scenario, wrt to profile to test
            # We already know that all target rules are part of the target profile
            params['profiles'] = [self.profile]
        return params

    # Check if a rule matches any of the targets to be tested
    # In CombinedChecker, we are looking for exact matches between rule and target
    def _matches_target(self, rule_dir, targets):
        for target in targets:
            # By prepending 'rule_', and match using endswith(), we should avoid
            # matching rules that are different by just a prefix of suffix
            if rule_dir.endswith("rule_"+target):
                return True, target
        return False, None


    def _test_target(self, target):
        try:
            remote_dir = send_scripts(self.test_env.domain_ip)
        except RuntimeError as exc:
            msg = "Unable to upload test scripts: {more_info}".format(more_info=str(exc))
            raise RuntimeError(msg)

        self._matching_rule_found = False

        with test_env.SavedState.create_from_environment(self.test_env, "tests_uploaded") as state:
            for rule in data.iterate_over_rules():
                matched, target_matched = self._matches_target(rule.directory, target)
                if not matched:
                    continue
                # In combined mode there is no expectations of matching substrings,
                # every entry in the target is expected to be unique.
                # Let's remove matched targets, so we can track rules not tested
                target.remove(target_matched)
                self._check_rule(rule, remote_dir, state)

        if len(target) != 0:
            logging.info("The following rule were not tested '{0}'".format(target))


def perform_combined_check(options):
    checker = CombinedChecker(options.test_env)

    checker.datastream = options.datastream
    checker.benchmark_id = options.benchmark_id
    checker.remediate_using = options.remediate_using
    checker.dont_clean = options.dont_clean
    # No debug option is provided for combined mode
    checker.manual_debug = False
    checker.benchmark_cpes = options.benchmark_cpes
    checker.scenarios_regex = options.scenarios_regex
    # Let's keep track of originaly targeted profile
    checker.profile = options.target

    profile = options.target
    # check if target is a complete profile ID, if not prepend profile prefix
    if not profile.startswith(OSCAP_PROFILE):
        profile = OSCAP_PROFILE+profile
    logging.info("Performing combined test using profile: {0}".format(profile))

    # Fetch target list from rules selected in profile
    target_rules = xml_operations.get_all_rule_ids_in_profile(
            options.datastream, options.benchmark_id,
            profile, logging)
    logging.debug("Profile {0} expanded to following list of "
                  "rules: {1}".format(profile, target_rules))

    checker.test_target(target_rules)
