#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2009, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of the Willow Garage nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import roslib
roslib.load_manifest('pr2_plugs_actions')

import rospy

import os,sys,time
import threading
import tf

from pr2_plugs_msgs.msg import *
from actionlib_msgs.msg import *
from move_base_msgs.msg import *
from pr2_common_action_msgs.msg import *
from pr2_plugs_actions.posestampedmath import PoseStampedMath
from std_srvs.srv import *
from executive_python import *

# State machine classes
from smach.state import *
from smach.state_machine import *
from smach.simple_action_state import *

import actionlib

class TFUtil():
  def __init__(self):
    # Construct tf listener
    transformer = tf.TransformListener(True, rospy.Duration(60.0))  

  def wait_and_transform(frame_id,pose):
    try:
      transformer.waitForTransform(frame_id, pose.header.frame_id, pose.header.stamp, rospy.Duration(2.0))
    except rospy.ServiceException, e:
      rospy.logerr('Could not transform between %s and %s' % (frame_id,pose.header.frame_id))
      raise e
    return transformer.transformPose(frame_id, pose)

def main():
  rospy.init_node("recharge_toplevel")

  # Static move base goal
  move_base_goal = MoveBaseGoal()
  move_base_goal.target_pose = PoseStampedMath().fromEuler(19.457, 16.099, 0.051, 0.014, -0.001, 1.192).msg
  move_base_goal.target_pose.header.stamp = rospy.Time.now()
  move_base_goal.target_pose.header.frame_id = "map"

  # Construct state machine
  sm = StateMachine('recharge',RechargeSMAction)
  # Define nominal sequence
  sm.add_sequence(
      # Meta-state for sending commands
      EmptyState('navigate_and_plugin'),
      # Tuck the arms
      SimpleActionState('tuck','tuck_arms',TuckArmsAction,
        goal = TuckArmsGoal(False,True,True)),
      # Navigate to the requested outlet
      SimpleActionState('navigate_to_outlet','move_base',MoveBaseAction,
        goal = move_base_goal),
      # Untuck the arms
      SimpleActionState('untuck','tuck_arms',TuckArmsAction,
        goal = TuckArmsGoal(True,False,True),aborted='untuck'),
      # Perform outlet detection
      SimpleActionState('detect_outlet','detect_outlet_sm',DetectOutletSMAction,
        goal = DetectOutletSMGoal(), aborted="navigate_to_outlet"),
      # Once we have the outlet pose, we will fetch the plug and plug in
      SimpleActionState('fetch_plug','fetch_plug_sm',FetchPlugAction,
        goal = FetchPlugGoal(), aborted='fetch_plug'),
      # Re-detect the plug in the gripper, plug, and wiggle in
      SimpleActionState('plugin','plugin',PluginAction,
        goal = PluginGoal(), aborted='detect_outlet')
      )

  # Populate the sm database with some stubbed out results
  # Run state machine action server with no default state
  sm.run_server()


if __name__ == "__main__":
  main()

