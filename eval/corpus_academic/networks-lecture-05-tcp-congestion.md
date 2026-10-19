# Computer Networks, Lecture 5: TCP congestion control

## Slow start and congestion avoidance
TCP starts with a congestion window of one segment and doubles it every round-trip time during slow start until it reaches the slow-start threshold. In congestion avoidance the window grows by one segment per round-trip time. A timeout resets the window to one segment; three duplicate acknowledgements halve it (fast recovery).

## CUBIC and BBR
Linux uses CUBIC by default, which grows the window as a cubic function of time since the last loss. BBR estimates bottleneck bandwidth and round-trip time instead of reacting to loss. The lecture notes that BBR version 1 can starve CUBIC flows on shared links, which is why the lab uses CUBIC on every host.

## Lab 2
Lab 2 measures throughput under 1 percent loss with CUBIC and with Reno. The expected result is that CUBIC recovers faster after loss; the report must include the congestion window plot captured with ss -ti.
