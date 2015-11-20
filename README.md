# RAMON
A distributed probabilistic rate monitoring function for node-local traffic rate modelling and congestion detection.

##Overview:
The rate monitoring function implements a link utilization tool for assessing the risk of congestion. The method is based on estimating the parameters of a log-normal distribution modeling observed byte rates. The parameters are estimated locally at the node at longer regular intervals, given observations of byte counters and updates of the statistical moments at significantly shorter time intervals, which allows for detecting persistent micro-congestion episodes. Inspection of the percentiles of the cumulative density function corresponding to 99% of the link capacity allows for indicating the risk of congestion at a predefined threshold. The result is a more precise way of estimating the risk, compared to the common practice of assessing the 5-min average traffic rates, in which micro-congestion episodes cannot be easily detected [1]. Querying counter statistics locally at high rates allows for accurately capturing important aspects the traffic behaviour with significantly lower overhead than in a centralized setting. By varying the querying rate, we can achieve flexible high quality monitoring without the cost of constant high rate sampling of the counters [2].	 

##Motivation:
Existing approaches (e.g. SNMP and sFlow) normally involve forwarding of raw measurement information to dedicated monitoring equipment for further processing, which impacts the scale at which monitoring can be efficiently performed and thereby the overall network observability. For this reason, standard practice for identifying increased bandwidth consumption is based on low-frequency counter inspections and reporting when the average exceeds a fixed threshold. Using such low-resolution averages often leads to missed congestion episodes as well as false alarms, as these averages usually are far below the link capacity and determination of suitable detection thresholds is difficult [3]. Performing computationally lightweight node-local analytics on the traffic rates, does not only enable a richer model of the observed data, but also allows for a more compact representation (in terms of estimated parameters) that with significantly lower overhead can be disseminated to another network management function for further processing.

##Features:
The implementation of the rate monitor will sample the traffic on the specified network interface and estimate the parameters of a log-normal distribution. The monitor can be run in two modes:

  1. A standalone program recording the data from the
     monitor (i.e. traffic rates and estimation parameters) in a text
     file in JSON format.

  2. Running in an OpenStack environment recording the monitor data in
     Ceilometer. (Se section "Storing the monitor data in Ceilometer"
     below).

For details on how to install and run the rate monitoring function, please see usage.html.

##Acknowledgement:
The research leading to these results has received funding from the European Union Seventh Framework Programme under grant agreement No. 619609 (see https://www.fp7-unify.eu/) and EIT ICT Labs Future Networking Solutions  Activity 15270 SDN@EDGE.

##Further reading and relevant work:
[1] P. Kreuger and R. Steinert, "Scalable in-network rate monitoring", Proc. IFIP/IEEE IM, Ottawa, Canada, May 2015.

[2] F. Németh, R. Steinert, P. Kreuger, and P. Sköldström, "Roles of DevOps tools in an automated, dynamic service creation architecture",IFIP/IEEE IM, Demo Session, Ottawa, Canada, May 2015.

[3] W. John, C. Meirosu, B. Pechenot, P. Sköldström, P. Kreuger and R. Steinert, "Scalable Software Defined Monitoring for Service Provider DevOps", Proc. EWSDN 2015, Bilbao, Spain, October 2015.
