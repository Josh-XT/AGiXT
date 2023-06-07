#!/bin/bash
export DOCKER_BUILDKIT=1
docker build -t agixt .
docker run agixt