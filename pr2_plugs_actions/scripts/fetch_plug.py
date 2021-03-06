#!/usr/bin/env python

import roslib
roslib.load_manifest('pr2_plugs_actions')

import rospy

import os,sys,time
from math import *
import copy
import tf
import PyKDL

from std_srvs.srv import *

from actionlib_msgs.msg import *
from pr2_plugs_msgs.msg import *
from pr2_common_action_msgs.msg import *
from pr2_controllers_msgs.msg import *
from trajectory_msgs.msg import *

from pr2_arm_move_ik.tools import *
from tf_conversions.posemath import fromMsg, toMsg
from geometry_msgs.msg import *
from joint_trajectory_action_tools.tools import get_action_goal as get_generator_goal

# State machine classes
from pr2_plugs_actions.tf_util import TFUtil
import smach
from smach import *
from smach_ros import *

import actionlib

__all__ = ['construct_sm']


def construct_sm():
    TFUtil()
    # Define fixed goals

    # Open gripper goal
    open_gripper_goal = Pr2GripperCommandGoal()
    open_gripper_goal.command.position = 0.07
    open_gripper_goal.command.max_effort = 99999

    # Close gripper goal
    close_gripper_goal = Pr2GripperCommandGoal()
    close_gripper_goal.command.position = 0.0
    close_gripper_goal.command.max_effort = 99999

    # Construct state machine
    sm = StateMachine(
            ['succeeded','aborted','preempted'],
            output_keys = ['plug_on_base_pose', 'gripper_plug_grasp_pose'])

    # Hardcoded poses for approach / grasping
    sm.userdata.gripper_plug_grasp_pose_approach = toMsg(PyKDL.Frame(PyKDL.Vector(0, 0.05, 0)).Inverse())
    sm.userdata.gripper_plug_grasp_pose = toMsg(PyKDL.Frame(PyKDL.Rotation.RPY(pi/2, 0.0, -pi/9), PyKDL.Vector(-0.03, 0.0, 0.005)).Inverse())

    # Define nominal sequence
    with sm:
        StateMachine.add('RAISE_SPINE',
                SimpleActionState('torso_controller/position_joint_action',
                    SingleJointPositionAction,
                    goal = SingleJointPositionGoal(position=0.16)),
                {'succeeded':'MOVE_ARM_BASE_DETECT_POSE'})

        # Move arm to detect the plug on the base
        StateMachine.add('MOVE_ARM_BASE_DETECT_POSE',
                         SimpleActionState('r_arm_controller/joint_trajectory_generator',
                                           JointTrajectoryAction, goal = get_generator_goal('pr2_plugs_configuration/detect_plug_on_base')),
                         {'succeeded':'DETECT_PLUG_ON_BASE'})

        # Detect the plug
        @smach.cb_interface(output_keys=['plug_on_base_pose'])
        def store_detect_plug_result(ud, result_state, result):
            if result_state == actionlib.GoalStatus.SUCCEEDED:
                ud.plug_on_base_pose = TFUtil.wait_and_transform('base_link', result.plug_pose).pose

        StateMachine.add('DETECT_PLUG_ON_BASE',
                SimpleActionState('detect_plug_on_base',DetectPlugOnBaseAction,
                    goal = DetectPlugOnBaseGoal(),
                    result_cb = store_detect_plug_result),
                         {'succeeded':'MOVE_ARM_BASE_GRASP_POSE',
                          'aborted':'MOVE_ARM_BASE_DETECT_POSE'})

        # Move arm to the grasp pose
        StateMachine.add('MOVE_ARM_BASE_GRASP_POSE',
                         SimpleActionState('r_arm_controller/joint_trajectory_generator',JointTrajectoryAction, goal = get_generator_goal('pr2_plugs_configuration/grasp_plug')),
                         {'succeeded':'OPEN_GRIPPER',
                          'aborted':'RECOVER_GRASP_TO_DETECT_POSE'})

        StateMachine.add('OPEN_GRIPPER',
                         SimpleActionState('r_gripper_controller/gripper_action',
                                           Pr2GripperCommandAction,
                                           goal = open_gripper_goal),
                         {'succeeded':'APPROACH_PLUG'})

        @smach.cb_interface(input_keys = ['plug_on_base_pose',
                                          'gripper_plug_grasp_pose_approach',
                                          'gripper_plug_grasp_pose'])
        def get_approach_plug_goal(ud, goal):
            """Get the ik goal for approaching the plug to grasp it """
            pose_gripper_wrist = fromMsg(TFUtil.wait_and_lookup('r_gripper_tool_frame', 'r_wrist_roll_link').pose)
            goal = ArmMoveIKGoal()
            goal.pose.pose = toMsg(fromMsg(ud.plug_on_base_pose)
                                   * fromMsg(ud.gripper_plug_grasp_pose_approach).Inverse()
                                   * fromMsg(ud.gripper_plug_grasp_pose).Inverse()
                                   * pose_gripper_wrist)

            goal.pose.header.stamp = rospy.Time.now()
            goal.pose.header.frame_id = 'base_link'
            goal.ik_seed = get_action_seed('pr2_plugs_configuration/grasp_plug_seed')
            goal.move_duration = rospy.Duration(3.0)

            return goal

        StateMachine.add('APPROACH_PLUG',
                         SimpleActionState('r_arm_ik', ArmMoveIKAction, goal_cb = get_approach_plug_goal),
                         {'succeeded':'GRASP_PLUG',
                          'aborted':'DETECT_PLUG_ON_BASE'})

        @smach.cb_interface(input_keys = ['plug_on_base_pose', 'gripper_plug_grasp_pose'])
        def get_grasp_plug_goal(ud, goal):
            """Get the ik goal for grasping the plug."""
            pose_gripper_wrist = fromMsg(TFUtil.wait_and_lookup('r_gripper_tool_frame', 'r_wrist_roll_link').pose)

            goal = ArmMoveIKGoal()
            goal.pose.pose = toMsg(fromMsg(ud.plug_on_base_pose)
                                   * fromMsg(ud.gripper_plug_grasp_pose).Inverse()
                                   * pose_gripper_wrist)

            goal.pose.header.stamp = rospy.Time.now()
            goal.pose.header.frame_id = 'base_link'
            goal.ik_seed = get_action_seed('pr2_plugs_configuration/grasp_plug_seed')
            goal.move_duration = rospy.Duration(3.0)

            return goal

        StateMachine.add('GRASP_PLUG',
                SimpleActionState('r_arm_ik', ArmMoveIKAction, goal_cb = get_grasp_plug_goal),
                {'succeeded':'CLOSE_GRIPPER',
                    'aborted':'DETECT_PLUG_ON_BASE'})
        
        StateMachine.add('CLOSE_GRIPPER',
                SimpleActionState('r_gripper_controller/gripper_action',
                    Pr2GripperCommandAction,
                    goal = close_gripper_goal),
                { 'succeeded':'DETECT_PLUG_ON_BASE',
                    'aborted':'REMOVE_PLUG'})

        StateMachine.add('REMOVE_PLUG',
                SimpleActionState('r_arm_controller/joint_trajectory_generator',JointTrajectoryAction, goal = get_generator_goal('pr2_plugs_configuration/remove_plug')),
                {'succeeded':'LOWER_SPINE'})
            
        StateMachine.add('LOWER_SPINE',
                SimpleActionState('torso_controller/position_joint_action',
                    SingleJointPositionAction,
                    goal = SingleJointPositionGoal(position=0.01)),
                {'succeeded':'succeeded'})
        
        # Define recovery states
        StateMachine.add('RECOVER_GRASP_TO_DETECT_POSE',
                SimpleActionState('r_arm_controller/joint_trajectory_generator',JointTrajectoryAction, goal = get_generator_goal('pr2_plugs_configuration/recover_grasp_to_detect')),
                { 'succeeded':'DETECT_PLUG_ON_BASE',
                    'aborted':'RECOVER_GRASP_TO_DETECT_POSE'})
    return sm

if __name__ == "__main__":
    rospy.init_node("fetch_plug")#,log_level=rospy.DEBUG)
    TFUtil()

    sm_fetch_plug = construct_sm()

    # Run state machine introspection server
    intro_server = IntrospectionServer('fetch_plug',sm_fetch_plug,'/RECHARGE/FETCH_PLUG')
    intro_server.start()

    # Run state machine action server 
    asw = ActionServerWrapper(
            'fetch_plug', FetchPlugAction, sm_fetch_plug,
            succeeded_outcomes = ['succeeded'],
            aborted_outcomes = ['aborted'],
            preempted_outcomes = ['preempted'],
            pack_result_slots = True)
    asw.run_server()

    rospy.spin()

    intro_server.stop()
