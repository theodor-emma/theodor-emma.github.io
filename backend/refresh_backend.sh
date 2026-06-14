#! /usr/bin/env bash

ssh ubuntu@api-rsvp.theodor-emma.fr "cd theodor-emma.github.io && git pull && systemctl --user restart backend.service && systemctl --user status backend.service"