#!/usr/bin/env python
# stub for plug detection action

import roslib; roslib.load_manifest('pr2_plugs_actions')
import rospy;
import actionlib;
from pr2_plugs_msgs.msg import *
from pr2_controllers_msgs.msg import *
from actionlib_msgs.msg import *
from trajectory_msgs.msg import JointTrajectoryPoint
from pr2_plugs_actions.posestampedmath import PoseStampedMath
from math import pi

#server actionlib.simple_action_server.SimpleActionServer

def execute_cb(goal):
  rospy.loginfo("Action server received goal")
  preempt_timeout = rospy.Duration(5.0)

  # move to joint space position
  rospy.loginfo("Move in joint space...")
  joint_space_goal.trajectory.header.stamp = rospy.Time.now()
  joint_space_goal.trajectory.joint_names = ['r_shoulder_pan_joint', 'r_shoulder_lift_joint', 'r_upper_arm_roll_joint', 'r_elbow_flex_joint', 'r_forearm_roll_joint', 'r_wrist_flex_joint', 'r_wrist_roll_joint']
  joint_space_goal.trajectory.points = [JointTrajectoryPoint([-1.1923984671080066, 0.73545055250367874, -3.7393139990349042, -1.5455017517279956, -2.0403840212157824, -1.8022484830811007, -3.1887412034226328], [], [], rospy.Duration(3.0))]
  if joint_space_client.send_goal_and_wait(joint_space_goal, rospy.Duration(10.0), preempt_timeout) != GoalStatus.SUCCEEDED:
    rospy.logerr('Move in joint space failed')
    server.set_aborted()
    return

  # call vision plug detection
  rospy.loginfo("Detecting plug...")
  detect_plug_goal.camera_name = "/forearm_camera_r"
  detect_plug_goal.prior = PoseStampedMath().fromEuler(-.03, 0, 0, pi/2, 0, -pi/6).inverse().msg
  detect_plug_goal.prior.header.stamp = rospy.Time.now()
  detect_plug_goal.prior.header.frame_id = "r_gripper_tool_frame"
  detect_plug_goal.origin_on_right = True
  if detect_plug_client.send_goal_and_wait(detect_plug_goal, rospy.Duration(10.0), preempt_timeout) != GoalStatus.SUCCEEDED:
    rospy.logerr('Vision plug detection failed')
    server.set_aborted()
    return

  # return result
  result = DetectPlugInGripperResult()
  result.plug_pose = detect_plug_client.get_result().plug_pose
  server.set_succeeded(result)
  rospy.loginfo("Action server goal finished")  


if __name__ == '__main__':
  #Initialize the node
  name = 'detect_plug'
  rospy.init_node(name)

  # create action clients we use
  joint_space_client = actionlib.SimpleActionClient('r_arm_plugs_controller/joint_trajectory_action', JointTrajectoryAction)
  joint_space_client.wait_for_server()
  joint_space_goal = JointTrajectoryGoal()

  detect_plug_client = actionlib.SimpleActionClient('vision_plug_detection', VisionPlugDetectionAction)
  detect_plug_client.wait_for_server()
  detect_plug_goal = VisionPlugDetectionGoal()
  rospy.loginfo('Connected to action clients')

  # create action server
  server = actionlib.simple_action_server.SimpleActionServer(name, DetectPlugInGripperAction, execute_cb)
  rospy.loginfo('%s: Action server running', name)


  rospy.spin()
