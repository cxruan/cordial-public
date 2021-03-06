#!/usr/bin/env python

#------------------------------------------------------------------------------
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#------------------------------------------------------------------------------


import roslib; roslib.load_manifest('cordial_sprite')
import rospy
import actionlib
import sys
from cordial_core.msg import *
from cordial_face.msg import *
import argparse
import json
import time

class DummyRobotServer:
    _feedback = BehaviorFeedback()
    _result = BehaviorResult()

    def __init__(self, behavior_file):

        self._server = actionlib.SimpleActionServer("Behavior", BehaviorAction, execute_cb=self.execute, auto_start=False)

        self._face_pub = rospy.Publisher('face', FaceRequest, queue_size=10)

        self._face_keyframe_pub = rospy.Publisher('face_keyframes', FaceKeyframeRequest, queue_size=10)

        rospy.sleep(0.5)

        self._server.start()
        rospy.loginfo("Ptbot Cordial server started.")

        #read in behaviors and keyframes from json file to dictonary
        rospy.loginfo("Loading keyframes from file... %s", behavior_file)
        with open(behavior_file,'r') as data_file:
            data = json.load(data_file)
            # Basic checks for keyframes file
            for key in data:
                if "dofs" not in data[key]:
                    rospy.logerr("Missing entry 'dofs' in behavior '%s'", key)
                if "keyframes" not in data[key]:
                    rospy.logerr("Missing entry 'keyframes' in behavior '%s'", key)
                for keyframe in data[key]["keyframes"]:
                    if "pose" not in keyframe:
                        rospy.logerr("Missing entry 'pose' in 'keyframes' of behavior '%s'", key)
                    if "time" not in keyframe:
                        rospy.logerr("Missing entry 'time' in 'keyframes' of behavior '%s'", key)
                    if "ending_action" not in keyframe:
                        rospy.logerr("Missing entry 'ending_action' in 'keyframes' of behavior '%s'", key)
                    if not len(keyframe["pose"]) == len(data[key]["dofs"]):
                        rospy.logerr("Unmatched length of 'dofs' and 'pose' in behavior '%s'", key)

        self.KF_behavior_dict = data
        rospy.loginfo("Done loading keyframes.")

    def play_face_keyframes(self, keyframes, times, dofs):
        # Play face keyframes
        face_indices = range(len(dofs))
        if len(face_indices)>0:
            face_frames = map(lambda k: [k[j] for j in face_indices], keyframes)
            face_frames = map(lambda l: Keyframe(positions=l), face_frames)
            face_dofs = [dofs[i] for i in face_indices]
            face_req = FaceKeyframeRequest(face_dofs=face_dofs, times = times, frames=face_frames)
            self._face_keyframe_pub.publish(face_req)


    def execute(self, goal):
        rospy.loginfo("Ptbot Cordial Server got goal: " + goal.behavior)

        success = True

        if self._server.is_preempt_requested():
            rospy.loginfo("Ptbot Cordial server preempted")
            self._server.set_preempted()
            success = False

        behavior = goal.behavior
        args = list(map(float, goal.args))

        if not behavior in self.KF_behavior_dict.keys():
            rospy.logwarn("Invalid behavior: " + behavior + ", ignoring.")
            success = False
        else:
            frames = self.KF_behavior_dict[behavior]["keyframes"]
            keyframes = map(lambda f: f["pose"], frames)
            times = map(lambda f: f["time"], frames)
            dofs = map(lambda s: str(s), self.KF_behavior_dict[behavior]["dofs"])

            if not len(args) == len(self.KF_behavior_dict[behavior].get("parameters", [])):
                # or set default values?
                rospy.logerr("Unmatched length of recieved args and paramaters in the keyframes file")
            elif len(args) > 0:
                # Build local dictionary for eval
                param_dict = {}
                for i in range(len(args)):
                    param = self.KF_behavior_dict[behavior]["parameters"][i]
                    param_dict[param] = args[i]
                    rospy.loginfo("Paramater " + param + ": " + str(args[i]))

                def eval_params(target, local_dict):
                    for i in range(len(target)):
                        # Only str will be evaluated
                        if isinstance(target[i], basestring):
                            print(target[i])
                            target[i] = eval(target[i], {'__builtins__': None}, local_dict)
                    return target

                keyframes = [eval_params(pose, param_dict) for pose in keyframes]
                times = eval_params(times, param_dict)

                for i in range(len(keyframes)):
                    for j in range(len(keyframes[i])):
                        if keyframes[i][j] < 0 or keyframes[i][j] > 1:
                            rospy.logwarn("pose %.2f at keyframe %d is out of bounds (0-1). Rounding it to %d", 
                                            keyframes[i][j], i, min(1, max(0, keyframes[i][j])))
                            keyframes[i][j] = min(1, max(0, keyframes[i][j]))

        # Play the face keyframes
        self.play_face_keyframes(keyframes, times, dofs)

        feedback = BehaviorFeedback(status=BehaviorFeedback.PLAYING)
        self._server.publish_feedback(feedback)

        if success:
            result = BehaviorResult(result=BehaviorResult.DONE)
            self._server.set_succeeded(result)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Controller for a dummy robot, so the face can be debugged')
    parser.add_argument('-b', '--behavior-file', help="Path to the json file containing keyframes for robot behaviors")
    args = parser.parse_known_args()[0]

    rospy.init_node("dummy_robot")

    behavior_file = args.behavior_file

    DummyRobotServer(behavior_file)

    while not rospy.is_shutdown():
        rospy.spin()
