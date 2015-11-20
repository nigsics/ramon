# ramon
A distributed probabilistic rate monitoring function for node-local traffic rate modelling and congestion detection

  The rate monitor will sample the traffic on the specified network
  interface and estimate the parameters of a log-normal
  distribution.

  The monitor can be run in two modes.

  1. A standalone program recording the data from the
     monitor (i.e. traffic rates and estimation parameters) in a text
     file in JSON format.

  2. Running in an OpenStack environment recording the monitor data in
     Ceilometer. (Se the section "Storing the monitor data in Ceilometer"
     in the file usage.html).

Installation and usage instructions are found in the file usage.html.
