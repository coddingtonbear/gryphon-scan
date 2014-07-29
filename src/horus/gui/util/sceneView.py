#!/usr/bin/python
# -*- coding: utf-8 -*-
#-----------------------------------------------------------------------#
#                                                                       #
# This file is part of the Horus Project                                #
#                                                                       #
# Copyright (C) 2014 Mundo Reader S.L.                                  #
# Copyright (C) 2013 David Braam from Cura Project                      #
#                                                                       #
# Date: June 2014                                                       #
# Author: Jesús Arroyo Torrens <jesus.arroyo@bq.com>                    #
#                                                                       #
# This program is free software: you can redistribute it and/or modify  #
# it under the terms of the GNU General Public License as published by  #
# the Free Software Foundation, either version 3 of the License, or     #
# (at your option) any later version.                                   #
#                                                                       #
# This program is distributed in the hope that it will be useful,       #
# but WITHOUT ANY WARRANTY; without even the implied warranty of        #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          #
# GNU General Public License for more details.                          #
#                                                                       #
# You should have received a copy of the GNU General Public License     #
# along with this program. If not, see <http://www.gnu.org/licenses/>.  #
#                                                                       #
#-----------------------------------------------------------------------#

__author__ = "Jesús Arroyo Torrens <jesus.arroyo@bq.com>"
__license__ = "GNU General Public License v3 http://www.gnu.org/licenses/gpl.html"

import wx
import numpy
import time
import os
import traceback
import threading
import math
import platform
import cStringIO as StringIO

import OpenGL
OpenGL.ERROR_CHECKING = False
from OpenGL.GLU import *
from OpenGL.GL import *

from horus.util import profile, resources, meshLoader, model
from horus.gui.util import openglHelpers
from horus.gui.util import openglGui

class SceneView(openglGui.glGuiPanel):
	def __init__(self, parent):
		super(SceneView, self).__init__(parent)

		self._yaw = 30
		self._pitch = 60
		self._zoom = 300
		self._object = None
		self._objectShader = None
		self._objectLoadShader = None
		self._focusObj = None
		self._selectedObj = None
		self._objColor = None
		self._mouseX = -1
		self._mouseY = -1
		self._mouseState = None
		self._viewTarget = numpy.array([0,0,0], numpy.float32)
		self._animView = None
		self._animZoom = None
		self._platformMesh = {}
		self._platformTexture = None

		self._viewport = None
		self._modelMatrix = None
		self._projMatrix = None
		self.tempMatrix = None

		self.viewMode = 'ply'

		self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
		self.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)

		self.updateProfileToControls()

	def createDefaultObject(self):
		self._clearScene()
		self._object = model.Model(None, isPointCloud=True)
		self._object._addMesh()
		self._object._mesh._prepareVertexCount(1000000)
		#self._object._postProcessAfterLoad()

	def appendPointCloud(self, point, color):
		if self._object is not None:
			mesh = self._object._mesh
			if mesh is not None:
				for i in range(len(point)):
					mesh._addVertex(point[i][0], point[i][1], point[i][2], color[i][0], color[i][1], color[i][2])
			self.QueueRefresh()

	def loadFile(self, filename):
		#-- Only one STL / PLY file can be active
		if filename is not None:
			ext = os.path.splitext(filename)[1].lower()
			if ext == '.ply' or ext == '.stl':
				modelFilename = filename
			if modelFilename:
				self.loadScene(modelFilename)
				self._selectedObj = self._object
				self._selectObject(self._object)

	def OnCenter(self, e):
		if self._focusObj is None:
			return
		self._focusObj.setPosition(numpy.array([0.0, 0.0]))
		newViewPos = numpy.array([self._focusObj.getPosition()[0], self._focusObj.getPosition()[1], self._focusObj.getSize()[2] / 2])
		self._animView = openglGui.animation(self, self._viewTarget.copy(), newViewPos, 0.5)

	def loadScene(self, filename):
		try:
			self._clearScene()
			self._object = meshLoader.loadMesh(filename)
		except:
			traceback.print_exc()

	def _clearScene(self):
		if self._object is not None:
			if self._object._mesh is not None:
				if self._object._mesh.vbo is not None and self._object._mesh.vbo.decRef():
					self.glReleaseList.append(self._object._mesh.vbo)
				self._object = None
			import gc
			gc.collect()

			newZoom = numpy.max(self._machineSize)
			self._animView = openglGui.animation(self, self._viewTarget.copy(), numpy.array([0,0,0], numpy.float32), 0.5)
			self._animZoom = openglGui.animation(self, self._zoom, newZoom, 0.5)

	def _selectObject(self, obj, zoom = True):
		if obj != self._selectedObj:
			self._selectedObj = obj
			self.updateModelSettingsToControls()
		if zoom and obj is not None:
			newViewPos = numpy.array([obj.getPosition()[0], obj.getPosition()[1], obj.getSize()[2] / 2])
			self._animView = openglGui.animation(self, self._viewTarget.copy(), newViewPos, 0.5)
			newZoom = obj.getBoundaryCircle() * 6
			if newZoom > numpy.max(self._machineSize) * 3:
				newZoom = numpy.max(self._machineSize) * 3
			self._animZoom = openglGui.animation(self, self._zoom, newZoom, 0.5)

	def updateProfileToControls(self):
		self._machineSize = numpy.array([profile.getMachineSettingFloat('machine_width'), profile.getMachineSettingFloat('machine_depth'), profile.getMachineSettingFloat('machine_height')])
		self._objColor = profile.getPreferenceColour('model_colour')
		self.updateModelSettingsToControls()

	def updateModelSettingsToControls(self):
		if self._selectedObj is not None:
			scale = self._selectedObj.getScale()
			size = self._selectedObj.getSize()

	def OnKeyChar(self, keyCode):
		if keyCode == wx.WXK_DELETE or keyCode == wx.WXK_NUMPAD_DELETE or (keyCode == wx.WXK_BACK and platform.system() == "Darwin"):
			if self._selectedObj is not None:
				self._deleteObject(self._selectedObj)
				self.QueueRefresh()
		if keyCode == wx.WXK_UP:
			if wx.GetKeyState(wx.WXK_SHIFT):
				self._zoom /= 1.2
				if self._zoom < 1:
					self._zoom = 1
			else:
				self._pitch -= 15
			self.QueueRefresh()
		elif keyCode == wx.WXK_DOWN:
			if wx.GetKeyState(wx.WXK_SHIFT):
				self._zoom *= 1.2
				if self._zoom > numpy.max(self._machineSize) * 3:
					self._zoom = numpy.max(self._machineSize) * 3
			else:
				self._pitch += 15
			self.QueueRefresh()
		elif keyCode == wx.WXK_LEFT:
			self._yaw -= 15
			self.QueueRefresh()
		elif keyCode == wx.WXK_RIGHT:
			self._yaw += 15
			self.QueueRefresh()
		elif keyCode == wx.WXK_NUMPAD_ADD or keyCode == wx.WXK_ADD or keyCode == ord('+') or keyCode == ord('='):
			self._zoom /= 1.2
			if self._zoom < 1:
				self._zoom = 1
			self.QueueRefresh()
		elif keyCode == wx.WXK_NUMPAD_SUBTRACT or keyCode == wx.WXK_SUBTRACT or keyCode == ord('-'):
			self._zoom *= 1.2
			if self._zoom > numpy.max(self._machineSize) * 3:
				self._zoom = numpy.max(self._machineSize) * 3
			self.QueueRefresh()
		elif keyCode == wx.WXK_HOME:
			self._yaw = 30
			self._pitch = 60
			self.QueueRefresh()
		elif keyCode == wx.WXK_PAGEUP:
			self._yaw = 0
			self._pitch = 0
			self.QueueRefresh()
		elif keyCode == wx.WXK_PAGEDOWN:
			self._yaw = 0
			self._pitch = 90
			self.QueueRefresh()
		elif keyCode == wx.WXK_END:
			self._yaw = 90
			self._pitch = 90
			self.QueueRefresh()

		if keyCode == wx.WXK_F3 and wx.GetKeyState(wx.WXK_SHIFT):
			shaderEditor(self, self.ShaderUpdate, self._objectLoadShader.getVertexShader(), self._objectLoadShader.getFragmentShader())
		if keyCode == wx.WXK_F4 and wx.GetKeyState(wx.WXK_SHIFT):
			from collections import defaultdict
			from gc import get_objects
			self._beforeLeakTest = defaultdict(int)
			for i in get_objects():
				self._beforeLeakTest[type(i)] += 1
		if keyCode == wx.WXK_F5 and wx.GetKeyState(wx.WXK_SHIFT):
			from collections import defaultdict
			from gc import get_objects
			self._afterLeakTest = defaultdict(int)
			for i in get_objects():
				self._afterLeakTest[type(i)] += 1
			for k in self._afterLeakTest:
				if self._afterLeakTest[k]-self._beforeLeakTest[k]:
					print k, self._afterLeakTest[k], self._beforeLeakTest[k], self._afterLeakTest[k] - self._beforeLeakTest[k]

	def ShaderUpdate(self, v, f):
		s = openglHelpers.GLShader(v, f)
		if s.isValid():
			self._objectLoadShader.release()
			self._objectLoadShader = s
			self.QueueRefresh()

	def OnMouseDown(self,e):
		self._mouseX = e.GetX()
		self._mouseY = e.GetY()
		self._mouseClick3DPos = self._mouse3Dpos
		self._mouseClickFocus = self._focusObj
		if e.ButtonDClick():
			self._mouseState = 'doubleClick'
		else:
			self._mouseState = 'dragOrClick'
		p0, p1 = self.getMouseRay(self._mouseX, self._mouseY)
		p0 -= self.getObjectCenterPos() - self._viewTarget
		p1 -= self.getObjectCenterPos() - self._viewTarget
		if self._mouseState == 'dragOrClick':
			if e.GetButton() == 1:
				if self._focusObj is not None:
					self._selectObject(self._focusObj, False)
					self.QueueRefresh()

	def OnMouseUp(self, e):
		if e.LeftIsDown() or e.MiddleIsDown() or e.RightIsDown():
			return
		if self._mouseState == 'dragOrClick':
			if e.GetButton() == 1:
				self._selectObject(self._object)
			if e.GetButton() == 3:
					menu = wx.Menu()
					if self._object is not None:
						self.Bind(wx.EVT_MENU, lambda e: self._clearScene(), menu.Append(-1, _("Delete object")))
					if menu.MenuItemCount > 0:
						self.PopupMenu(menu)
					menu.Destroy()
		self._mouseState = None

	def OnMouseMotion(self,e):
		p0, p1 = self.getMouseRay(e.GetX(), e.GetY())
		p0 -= self.getObjectCenterPos() - self._viewTarget
		p1 -= self.getObjectCenterPos() - self._viewTarget

		if e.Dragging() and self._mouseState is not None:
			if e.LeftIsDown() and not e.RightIsDown():
				self._mouseState = 'drag'
				if wx.GetKeyState(wx.WXK_SHIFT):
					a = math.cos(math.radians(self._yaw)) / 3.0
					b = math.sin(math.radians(self._yaw)) / 3.0
					self._viewTarget[0] += float(e.GetX() - self._mouseX) * -a
					self._viewTarget[1] += float(e.GetX() - self._mouseX) * b
					self._viewTarget[0] += float(e.GetY() - self._mouseY) * b
					self._viewTarget[1] += float(e.GetY() - self._mouseY) * a
				else:
					self._yaw += e.GetX() - self._mouseX
					self._pitch -= e.GetY() - self._mouseY
				if self._pitch > 170:
					self._pitch = 170
				if self._pitch < 10:
					self._pitch = 10
			elif (e.LeftIsDown() and e.RightIsDown()) or e.MiddleIsDown():
				self._mouseState = 'drag'
				self._zoom += e.GetY() - self._mouseY
				if self._zoom < 1:
					self._zoom = 1
				if self._zoom > numpy.max(self._machineSize) * 3:
					self._zoom = numpy.max(self._machineSize) * 3

		self._mouseX = e.GetX()
		self._mouseY = e.GetY()

	def OnMouseWheel(self, e):
		delta = float(e.GetWheelRotation()) / float(e.GetWheelDelta())
		delta = max(min(delta,4),-4)
		self._zoom *= 1.0 - delta / 10.0
		if self._zoom < 1.0:
			self._zoom = 1.0
		if self._zoom > numpy.max(self._machineSize) * 3:
			self._zoom = numpy.max(self._machineSize) * 3
		self.Refresh()

	def OnMouseLeave(self, e):
		#self._mouseX = -1
		pass

	def getMouseRay(self, x, y):
		if self._viewport is None:
			return numpy.array([0,0,0],numpy.float32), numpy.array([0,0,1],numpy.float32)
		p0 = openglHelpers.unproject(x, self._viewport[1] + self._viewport[3] - y, 0, self._modelMatrix, self._projMatrix, self._viewport)
		p1 = openglHelpers.unproject(x, self._viewport[1] + self._viewport[3] - y, 1, self._modelMatrix, self._projMatrix, self._viewport)
		p0 -= self._viewTarget
		p1 -= self._viewTarget
		return p0, p1

	def _init3DView(self):
		# set viewing projection
		size = self.GetSize()
		glViewport(0, 0, size.GetWidth(), size.GetHeight())
		glLoadIdentity()

		glLightfv(GL_LIGHT0, GL_POSITION, [0.2, 0.2, 1.0, 0.0])

		glDisable(GL_RESCALE_NORMAL)
		glDisable(GL_LIGHTING)
		glDisable(GL_LIGHT0)
		glEnable(GL_DEPTH_TEST)
		glDisable(GL_CULL_FACE)
		glDisable(GL_BLEND)
		glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

		#glClearColor(0.0, 0.0, 0.0, 1.0)
		#glClearStencil(0)
		#glClearDepth(1.0)

		glMatrixMode(GL_PROJECTION)
		glLoadIdentity()
		aspect = float(size.GetWidth()) / float(size.GetHeight())
		gluPerspective(45.0, aspect, 1.0, numpy.max(self._machineSize) * 4)

		glMatrixMode(GL_MODELVIEW)
		glLoadIdentity()

		glBegin(GL_QUADS)
		glColor3f(1,1,1)
		glVertex3f (-1,-1,-1)
		glVertex3f (1,-1,-1)
		glColor3f(0,0,0)
		glVertex3f (1,1,-1)
		glVertex3f (-1,1,-1)
		glEnd()

		glClear(GL_DEPTH_BUFFER_BIT)
		#glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)
			
	def OnPaint(self,e):
		if self._animView is not None:
			self._viewTarget = self._animView.getPosition()
			if self._animView.isDone():
				self._animView = None
		if self._animZoom is not None:
			self._zoom = self._animZoom.getPosition()
			if self._animZoom.isDone():
				self._animZoom = None
		if self._objectShader is None: #TODO: add loading shaders from file(s)
			if openglHelpers.hasShaderSupport():
				self._objectShader = openglHelpers.GLShader("""
					varying float light_amount;

					void main(void)
					{
						gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
						gl_FrontColor = gl_Color;

						light_amount = abs(dot(normalize(gl_NormalMatrix * gl_Normal), normalize(gl_LightSource[0].position.xyz)));
						light_amount += 0.2;
					}
									""","""
					varying float light_amount;

					void main(void)
					{
						gl_FragColor = vec4(gl_Color.xyz * light_amount, gl_Color[3]);
					}
				""")
				self._objectShaderNoLight = openglHelpers.GLShader("""
					varying float light_amount;

					void main(void)
					{
						gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
						gl_FrontColor = gl_Color;

						light_amount = 1.0;
					}
									""","""
					varying float light_amount;

					void main(void)
					{
						gl_FragColor = vec4(gl_Color.xyz * light_amount, gl_Color[3]);
					}
				""")
				self._objectLoadShader = openglHelpers.GLShader("""
					uniform float intensity;
					uniform float scale;
					varying float light_amount;

					void main(void)
					{
						vec4 tmp = gl_Vertex;
						tmp.x += sin(tmp.z/5.0+intensity*30.0) * scale * intensity;
						tmp.y += sin(tmp.z/3.0+intensity*40.0) * scale * intensity;
						gl_Position = gl_ModelViewProjectionMatrix * tmp;
						gl_FrontColor = gl_Color;

						light_amount = abs(dot(normalize(gl_NormalMatrix * gl_Normal), normalize(gl_LightSource[0].position.xyz)));
						light_amount += 0.2;
					}
			""","""
				uniform float intensity;
				varying float light_amount;

				void main(void)
				{
					gl_FragColor = vec4(gl_Color.xyz * light_amount, 1.0-intensity);
				}
				""")
			if self._objectShader is None or not self._objectShader.isValid(): #Could not make shader.
				self._objectShader = openglHelpers.GLFakeShader()
				self._objectLoadShader = None

		self._init3DView()
		glTranslate(0,0,-self._zoom)
		glRotate(-self._pitch, 1,0,0)
		glRotate(self._yaw, 0,0,1)
		glTranslate(-self._viewTarget[0],-self._viewTarget[1],-self._viewTarget[2])

		self._viewport = glGetIntegerv(GL_VIEWPORT)
		self._modelMatrix = glGetDoublev(GL_MODELVIEW_MATRIX)
		self._projMatrix = glGetDoublev(GL_PROJECTION_MATRIX)

		glClearColor(1,1,1,1)
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)

		if self._mouseX > -1: # mouse has not passed over the opengl window.
			glFlush()
			n = glReadPixels(self._mouseX, self.GetSize().GetHeight() - 1 - self._mouseY, 1, 1, GL_RGBA, GL_UNSIGNED_INT_8_8_8_8)[0][0] >> 8
			self._focusObj = self._object
			f = glReadPixels(self._mouseX, self.GetSize().GetHeight() - 1 - self._mouseY, 1, 1, GL_DEPTH_COMPONENT, GL_FLOAT)[0][0]
			#self.GetTopLevelParent().SetTitle(hex(n) + " " + str(f))
			self._mouse3Dpos = openglHelpers.unproject(self._mouseX, self._viewport[1] + self._viewport[3] - self._mouseY, f, self._modelMatrix, self._projMatrix, self._viewport)
			self._mouse3Dpos -= self._viewTarget

		self._init3DView()
		glTranslate(0,0,-self._zoom)
		glRotate(-self._pitch, 1,0,0)
		glRotate(self._yaw, 0,0,1)
		glTranslate(-self._viewTarget[0],-self._viewTarget[1],-self._viewTarget[2])

		glStencilFunc(GL_ALWAYS, 1, 1)
		glStencilOp(GL_INCR, GL_INCR, GL_INCR)

		if self._object is not None:

			if self._object.isPointCloud():
				self._objectShaderNoLight.bind()
			else:
				self._objectShader.bind()

			brightness = 1.0
			if self._focusObj == self._object:
				brightness = 1.2
			elif self._focusObj is not None or self._selectedObj is not None and self._object != self._selectedObj:
				brightness = 0.8

			if self._selectedObj == self._object or self._selectedObj is None:
				glStencilOp(GL_INCR, GL_INCR, GL_INCR)
				glEnable(GL_STENCIL_TEST)
			self._renderObject(self._object, brightness)

			glDisable(GL_STENCIL_TEST)
			glDisable(GL_BLEND)
			glEnable(GL_DEPTH_TEST)
			glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)

			if self._object.isPointCloud():
				self._objectShaderNoLight.unbind()
			else:
				self._objectShader.unbind()

			glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
			glEnable(GL_BLEND)
			if self._objectLoadShader is not None:
				#self._objectLoadShader.bind()
				#glColor4f(0.2, 0.6, 1.0, 1.0)
				#self._objectLoadShader.setUniform('intensity', self._object._.getPosition())
				#self._objectLoadShader.setUniform('scale', self._object.getBoundaryCircle() / 10)
				self._renderObject(self._object)
				#self._objectLoadShader.unbind()
				glDisable(GL_BLEND)

		self._drawMachine()

	def _renderObject(self, obj, brightness = 0):
		glPushMatrix()
		glTranslate(obj.getPosition()[0], obj.getPosition()[1], obj.getSize()[2] / 2)

		if self.tempMatrix is not None and obj == self._selectedObj:
			glMultMatrixf(openglHelpers.convert3x3MatrixTo4x4(self.tempMatrix))

		offset = obj.getDrawOffset()
		glTranslate(-offset[0], -offset[1], -offset[2] - obj.getSize()[2] / 2)

		glMultMatrixf(openglHelpers.convert3x3MatrixTo4x4(obj.getMatrix()))

		if obj.isPointCloud():
			if obj._mesh is not None:
				if obj._mesh.vbo is not None:
					obj._mesh.vbo.release()
				obj._mesh.vbo = openglHelpers.GLVBO(GL_POINTS, obj._mesh.vertexes, colorArray=obj._mesh.colors)
				obj._mesh.vbo.render()
		else:
			if obj._mesh is not None:
				if obj._mesh.vbo is not None:
					obj._mesh.vbo.release()
				obj._mesh.vbo = openglHelpers.GLVBO(GL_TRIANGLES, obj._mesh.vertexes, obj._mesh.normal)
				if brightness != 0:
					glColor4fv(map(lambda idx: idx * brightness, self._objColor))
				obj._mesh.vbo.render()
		glPopMatrix()

	def _drawMachine(self):
		glEnable(GL_CULL_FACE)
		glEnable(GL_BLEND)

		size = [profile.getMachineSettingFloat('machine_width'), profile.getMachineSettingFloat('machine_depth'), profile.getMachineSettingFloat('machine_height')]

		machine = profile.getMachineSetting('machine_type')
		if machine.startswith('cyclops'):

			#-- Platform
			if machine not in self._platformMesh:
				mesh = meshLoader.loadMesh(resources.getPathForMesh(machine + '_platform.stl'))
				if mesh is not None:
					self._platformMesh[machine] = mesh
				else:
					self._platformMesh[machine] = None
				self._platformMesh[machine]._drawOffset = numpy.array([0,0,13.6], numpy.float32)
			glColor4f(0.6,0.6,0.6,0.5)
			self._objectShader.bind()
			self._renderObject(self._platformMesh[machine], False)
			self._objectShader.unbind()

			#-- Text
			"""
			if not hasattr(self._platformMesh[machine], 'texture'):
				self._platformMesh[machine].texture = openglHelpers.loadGLTexture('Cyclopsbackplate.png')
			glBindTexture(GL_TEXTURE_2D, self._platformMesh[machine].texture)
			glEnable(GL_TEXTURE_2D)
			glPushMatrix()
			glColor4f(1,1,1,1)
			glTranslate(0,150,0)
			h = 50
			d = 8
			w = 100
			glEnable(GL_BLEND)
			glBlendFunc(GL_DST_COLOR, GL_ZERO)
			glBegin(GL_QUADS)
			glTexCoord2f(1, 0)
			glVertex3f( w, 0, h)
			glTexCoord2f(0, 0)
			glVertex3f(-w, 0, h)
			glTexCoord2f(0, 1)
			glVertex3f(-w, 0, 0)
			glTexCoord2f(1, 1)
			glVertex3f( w, 0, 0)

			glTexCoord2f(1, 0)
			glVertex3f(-w, d, h)
			glTexCoord2f(0, 0)
			glVertex3f( w, d, h)
			glTexCoord2f(0, 1)
			glVertex3f( w, d, 0)
			glTexCoord2f(1, 1)
			glVertex3f(-w, d, 0)
			glEnd()
			glDisable(GL_TEXTURE_2D)
			glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
			glPopMatrix()"""

			#-- Coordinate system
			"""
			glColor4f(0,0,0,1)
			glLineWidth(3)
			glBegin(GL_LINES)
			glVertex3f(-size[0] / 2, -size[1] / 2, 0)
			glVertex3f(-size[0] / 2, -size[1] / 2, 10)
			glVertex3f(-size[0] / 2, -size[1] / 2, 0)
			glVertex3f(-size[0] / 2+10, -size[1] / 2, 0)
			glVertex3f(-size[0] / 2, -size[1] / 2, 0)
			glVertex3f(-size[0] / 2, -size[1] / 2+10, 0)
			glEnd()"""

		glDepthMask(False)

		
		polys = profile.getMachineSizePolygons()
		height = profile.getMachineSettingFloat('machine_height')
		circular = profile.getMachineSetting('machine_shape') == 'Circular'

		"""
		glBegin(GL_QUADS)
		# Draw the sides of the build volume.
		for n in xrange(0, len(polys[0])):
			if not circular:
				if n % 2 == 0:
					glColor4ub(5, 171, 231, 96)
				else:
					glColor4ub(5, 171, 231, 64)
			else:
				#glColor4ub(5, 171, 231, 96)
				glColor4ub(200, 200, 200, 60)

			glVertex3f(polys[0][n][0], polys[0][n][1], height)
			glVertex3f(polys[0][n][0], polys[0][n][1], 0)
			glVertex3f(polys[0][n-1][0], polys[0][n-1][1], 0)
			glVertex3f(polys[0][n-1][0], polys[0][n-1][1], height)
		glEnd()

		#Draw top of build volume.
		#glColor4ub(5, 171, 231, 128)
		glColor4ub(200, 200, 200, 70)
		glBegin(GL_TRIANGLE_FAN)
		for p in polys[0][::-1]:
			glVertex3f(p[0], p[1], height)
		glEnd()"""

		#-- Draw checkerboard
		if self._platformTexture is None:
			self._platformTexture = openglHelpers.loadGLTexture('checkerboard.png')
			glBindTexture(GL_TEXTURE_2D, self._platformTexture)
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
		glColor4f(1,1,1,0.5)
		glBindTexture(GL_TEXTURE_2D, self._platformTexture)
		glEnable(GL_TEXTURE_2D)
		glBegin(GL_TRIANGLE_FAN)
		for p in polys[0]:
			glTexCoord2f(p[0]/20, p[1]/20)
			glVertex3f(p[0], p[1], 0)
		glEnd()

		"""
		#Draw no-go zones. (clips in case of UM2)
		glDisable(GL_TEXTURE_2D)
		glColor4ub(127, 127, 127, 200)
		for poly in polys[1:]:
			glBegin(GL_TRIANGLE_FAN)
			for p in poly:
				glTexCoord2f(p[0]/20, p[1]/20)
				glVertex3f(p[0], p[1], 0)
			glEnd()"""

		glDepthMask(True)
		glDisable(GL_BLEND)
		glDisable(GL_CULL_FACE)

	def getObjectCenterPos(self):
		if self._selectedObj is None:
			return [0.0, 0.0, 0.0]
		pos = self._selectedObj.getPosition()
		size = self._selectedObj.getSize()
		return [pos[0], pos[1], size[2]/2]

	def getObjectBoundaryCircle(self):
		if self._selectedObj is None:
			return 0.0
		return self._selectedObj.getBoundaryCircle()

	def getObjectSize(self):
		if self._selectedObj is None:
			return [0.0, 0.0, 0.0]
		return self._selectedObj.getSize()

	def getObjectMatrix(self):
		if self._selectedObj is None:
			return numpy.matrix(numpy.identity(3))
		return self._selectedObj.getMatrix()

#TODO: Remove this or put it in a seperate file
class shaderEditor(wx.Dialog):
	def __init__(self, parent, callback, v, f):
		super(shaderEditor, self).__init__(parent, title="Shader editor", style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
		self._callback = callback
		s = wx.BoxSizer(wx.VERTICAL)
		self.SetSizer(s)
		self._vertex = wx.TextCtrl(self, -1, v, style=wx.TE_MULTILINE)
		self._fragment = wx.TextCtrl(self, -1, f, style=wx.TE_MULTILINE)
		s.Add(self._vertex, 1, flag=wx.EXPAND)
		s.Add(self._fragment, 1, flag=wx.EXPAND)

		self._vertex.Bind(wx.EVT_TEXT, self.OnText, self._vertex)
		self._fragment.Bind(wx.EVT_TEXT, self.OnText, self._fragment)

		self.SetPosition(self.GetParent().GetPosition())
		self.SetSize((self.GetSize().GetWidth(), self.GetParent().GetSize().GetHeight()))
		self.Show()

	def OnText(self, e):
		self._callback(self._vertex.GetValue(), self._fragment.GetValue())