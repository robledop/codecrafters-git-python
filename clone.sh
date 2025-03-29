#!/usr/bin/env bash

rm -rf ./git-sample-1
GIT_TRACE_CURL=1 git -c http.sslVerify=false -c http.proxy=localhost:8080 clone https://github.com/codecrafters-io/git-sample-1 