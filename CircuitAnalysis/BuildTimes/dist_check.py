#!/usr/bin/env python
# Checks the distribution of circuits 

try:
  import psyco
  psyco.full()
except ImportError:
  #print 'Psyco not installed, the program will just run slower'
  pass

#import profile

import socket,sys,time,getopt
sys.path.append("../../")
import TorCtl
from TorCtl.TorUtil import meta_port,meta_host,control_port,control_host,control_pass
from TorCtl import StatsSupport
from TorCtl.StatsSupport import StatsHandler
from TorCtl import PathSupport, TorCtl
from TorCtl.PathSupport import ExitPolicyRestriction,OrNodeRestriction
from TorCtl.TorUtil import plog

# XXX: This router is in both buildtimes and dist_check
# Probably should be in its own file..
class BTRouter(StatsSupport.StatsRouter):
  def __init__(self, router):
    StatsSupport.StatsRouter.__init__(self, router)
 
  def reset(self):
    StatsSupport.StatsRouter.reset(self)
    self.chosen = [0,0,0]
    self.uptime = 0 # XXX: Redundant? current_uptime() is also a method..

def usage():
  print "Option fail."

def getargs():
  if len(sys.argv[1:]) < 2:
    usage()
    sys.exit(2)

  pathfile=None
  try:
    opts,args = getopt.getopt(sys.argv[1:],"f:")
  except getopt.GetoptError,err:
    print str(err)
    usage()
  for o,a in opts:
    if o == '-f': 
      pathfile = a
    else:
      assert False, "Bad option"
  return pathfile


def min_avg_max(l):
  minr = 2**30
  maxr = 0
  avgr = 0.0
  for v in l:
    avgr += v
    if v < minr: minr = v
    if v > maxr: maxr = v
  avgr /= len(l)
  return (minr,avgr,maxr)

def check_ranks(r):
  if not r.rank_history:
    return (r.list_rank, r.list_rank, r.list_rank)
  return min_avg_max(r.rank_history)

def open_controller():
  """ starts stat gathering thread """
  s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
  s.connect((control_host,control_port))
  c = PathSupport.Connection(s)
  c.authenticate(control_pass)  # also launches thread...
  return c

def run_check(routers, pathfile, log, disk_only=False):
  for i in xrange(len(routers)):
    if routers[i].list_rank != i:
      log("WARN: List unsorted at position "+str(i)+", "+routers[i].idhex)

  router_map = {}
  for r in routers:
    router_map[r.idhex] = r

  f = open(pathfile+".nodes", "r")
  ok_circs = f.readlines()
  f.close()
    
  f = open(pathfile+".failed", "r")
  failed_circs = f.readlines()
  f.close()

  uptimes = open(pathfile+".uptime", "r")
  total_absent = 0
  total_present = 0
  for line in uptimes:
    nodes = map(lambda n: n.strip(), line.split("\t"))
    if nodes[0] in router_map:
      total_present += 1
      router_map[nodes[0]].uptime = float(nodes[1])/60.0
    else:
      total_absent += 1
  uptimes.close()

  pct_mins = [100, 100, 100]
  pct_maxes = [0, 0, 0]
  flags = [{},{},{}]
  present={}
  absent={}
  circuits=0

  exit_check = OrNodeRestriction([
                  ExitPolicyRestriction("255.255.255.255", 80),
                  ExitPolicyRestriction("255.255.255.255", 443)])
   
  exit_fails={}

  for line in ok_circs+failed_circs:
    nodes = map(lambda n: n.strip(), line.split("\t"))
    cid,nodes = (nodes[0],nodes[1:])
    circuits+=1
    for i in xrange(0, len(nodes)):
      if nodes[i] not in router_map:
        #log(nodes[i] + " no longer present in map")
        absent[nodes[i]] = 1
        continue
      present[nodes[i]] = 1
      router_map[nodes[i]].chosen[i] += 1
      pct = 100.0*router_map[nodes[i]].list_rank/len(routers)
      if pct < pct_mins[i]:
        pct_mins[i] = pct
      if pct > pct_maxes[i]:
        pct_maxes[i] = pct
      def flag_ctr(f):
        if not f in flags[i]: flags[i][f] = 0
        flags[i][f] += 1
      map(flag_ctr, router_map[nodes[i]].flags)

    if nodes[2] in router_map:
      if not exit_check.r_is_ok(router_map[nodes[2]]):
        if not nodes[2] in exit_fails: exit_fails[nodes[2]] = 1
        else: exit_fails[nodes[2]] += 1

  for e in exit_fails.iterkeys():
    log("WARN: "+str(exit_fails[e])+"/"+str(router_map[e].chosen[2])+" exit policy mismatches using exit "+e)
    log("Exit policy:")
    for p in router_map[e].exitpolicy:
      log(" "+str(p))
    log(" 80: "+str(router_map[e].will_exit_to("255.255.255.255", 80)))
    log(" 443: "+str(router_map[e].will_exit_to("255.255.255.255", 443)))


  # FIXME: Compare chosen/n_circuits to weighted %bw. 
  # Multiply by pct_min+max

  tot_len = len(routers)

  # FIXME: Read in from files, compare against saved infoz
  rankfile = open(pathfile+".ranks", "r")
  for line in rankfile:
    nodes = map(lambda n: n.strip(), line.split(" "))
    ranks = []
    bws = []
    if nodes[0] == 'r': # rank list
      ranks = map(int, nodes[2:])   
    elif nodes[0] == 'b': # bw list
      bws = map(int, nodes[2:])
    if nodes[1] in router_map:
      router = router_map[nodes[1]]
      if disk_only:
        if ranks: router.rank_history = ranks
        if bws: router.bw_history = bws
        continue
    elif disk_only:
        continue  

    if len(ranks) > 1 and not router.rank_history:
      print "WARN: Rank storage mismatch for "+router.idhex
      continue
    if len(bws) > 1 and not router.bw_history:
      print "WARN: Bw storage mismatch for "+router.idhex
      continue

    if router.rank_history and ranks:
      if len(ranks) != len(router.rank_history):
          print "WARN: Rank mismatch for "+router.idhex+": "+str(check_ranks(router))+" vs "+str(min_avg_max(ranks))
          print " local: "+str(router.rank_history)
          print " disk: "+str(ranks)
      for i,r in enumerate(ranks):
        if router.rank_history[i] != r:
          print "WARN: Rank mismatch for "+router.idhex+": "+str(check_ranks(router))+" vs "+str(min_avg_max(ranks))
          print " local: "+str(router.rank_history)
          print " disk: "+str(ranks)
          break
    if router.bw_history and bws:
      if len(bws) != len(router.bw_history):
          print "WARN: Bw mismatch for "+router.idhex+": "+str(check_ranks(router))+" vs "+str(min_avg_max(ranks))
          print " local: "+str(router.bw_history)
          print " disk: "+str(bws)
      else:
        for i,b in enumerate(bws):
          if router.bw_history[i] != b:
            print "WARN: Bw mismatch for "+router.idhex+": "+str(check_ranks(router))+" vs "+str(min_avg_max(ranks))
            print " local: "+str(router.bw_history)
            print " disk: "+str(bws)
            break
  rankfile.close()

  for i in xrange(0, 3):
    routers.sort(lambda x, y: cmp(y.chosen[i], x.chosen[i]))
    log("\nHop "+str(i)+": ")
    unchosen = 0
    for r in routers:
      if r.chosen[i] == 0: unchosen+=1
      else:
        ranks = check_ranks(r) 
        log(r.idhex+" "+("/".join(map(lambda f: str(round(100.0*f/tot_len, 1)), ranks)))+"%\tchosen: "+str(r.chosen[i])+"\tup: "+str(round(r.uptime,1)))
        #log(r.idhex+" "+str(round((100.0*r.list_rank)/len(routers),2))+"%, chosen: "+str(r.chosen[i])+", up: "+str(round(r.uptime,2)))

    log("Nodes not chosen for this hop: "+str(unchosen)+"/"+str(len(routers)))

    flgs = flags[i].keys()
    flgs.sort(lambda x, y: cmp(y,x))
    for f in flgs:
      if flags[i][f] == circuits:
        log(f+": "+str(flags[i][f])+" (all)")
      else:
        log(f+": "+str(flags[i][f]))

  # FIXME: Print out summaries for failure information for some routers
  
  log("Routers used that are still present: "+str(len(present.keys())))
  log("Routers used that are now absent: "+str(len(absent.keys())))
  log("Routers considered that are still present: "+str(total_present))
  log("Routers considered that are now absent: "+str(total_absent))
  log("Min percentiles per hop: "+str(pct_mins))
  log("Max percentiles per hop: "+str(pct_maxes))

def logger(msg):
  print msg

def main():
  pathfile = getargs()
  c=open_controller()  
  routers = map(BTRouter, c.read_routers(c.get_network_status())) 
  routers.sort(lambda x, y: cmp(y.bw, x.bw))
  for i in xrange(len(routers)): routers[i].list_rank = i
  run_check(routers, pathfile, logger, True)

if __name__ == '__main__':
  main()

