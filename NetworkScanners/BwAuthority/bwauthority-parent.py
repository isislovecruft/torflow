#!/usr/bin/env python
import sys
import subprocess
import ConfigParser
import os
import traceback
sys.path.append("../../")
from TorCtl import TorUtil
from TorCtl.TorUtil import plog
import bwauthority

p = None

def main(argv):
  TorUtil.read_config(argv[1])
  (start_pct,stop_pct,nodes_per_slice,save_every,circs_per_node,out_dir,
      max_fetch_time,tor_dir,sleep_start,sleep_stop,
             min_streams,pid_file_name) = bwauthority.read_config(argv[1])
 
  if pid_file_name:
    pidfd = file(pid_file_name, 'w')
    pidfd.write('%d\n' % os.getpid())
    pidfd.close()

  slice_num = 0 
  while True:
    plog('INFO', 'Beginning time loop')

    p = subprocess.Popen("python bwauthority.py %s %s" %
            (argv[1], str(slice_num)),shell=True)
    p.wait()
    if (p.returncode == 0):
      slice_num += 1
    elif (p.returncode == bwauthority.STOP_PCT_REACHED):
      slice_num = 0
    else:
      plog('WARN', 'Child process returned %s' % p.returncode)

if __name__ == '__main__':
  try:
    main(sys.argv)
  except KeyboardInterrupt:
    p.terminate()
    plog('INFO', "Ctrl + C was pressed. Exiting ... ")
    traceback.print_exc()
  except Exception, e:
    plog('ERROR', "An unexpected error occured.")
    traceback.print_exc()