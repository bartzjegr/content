#!/bin/bash
#
# profiles = xccdf_org.ssgproject.content_profile_stig

yum install -y chrony
yum remove -y ntp

if ! grep "^server.*maxpoll 10" /etc/chrony.conf; then
    sed -i "s/^server.*/& maxpoll 10/" /etc/chrony.conf
fi

systemctl enable chronyd.service