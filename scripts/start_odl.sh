#!/bin/bash
echo "Starting OpenDaylight..."
~/sr-testbed/odl/bin/start
sleep 5
echo "Waiting for PCEP port 1970..."
while ! ss -tlnp | grep -q 1790; do sleep 2; done
echo "ODL ready on port 1790"
