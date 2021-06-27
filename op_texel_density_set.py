import bpy
import bmesh
import mathutils
from mathutils import Vector
import math

from . import utilities_texel
from . import utilities_uv


class op(bpy.types.Operator):
	bl_idname = "uv.textools_texel_density_set"
	bl_label = "Set Texel size"
	bl_description = "Apply texel density by scaling the UV's to match the ratio"
	bl_options = {'REGISTER', 'UNDO'}
	
	@classmethod
	def poll(cls, context):

		if not bpy.context.active_object:
			return False
		
		if bpy.context.object.mode != 'EDIT' and bpy.context.object.mode != 'OBJECT':
			return False

		if bpy.context.object.mode == 'OBJECT' and len(bpy.context.selected_objects) == 0:
			return False
		
		if bpy.context.active_object.type != 'MESH':
			return False

		#Only in UV editor mode
		if bpy.context.area.type != 'IMAGE_EDITOR':
			return False

		#Requires UV map
		if not bpy.context.object.data.uv_layers:
			return False

		# if bpy.context.object.mode == 'EDIT':
		# 	# In edit mode requires face select mode
		# 	if bpy.context.scene.tool_settings.mesh_select_mode[2] == False:
		# 		return False	

		return True

	
	def execute(self, context):
		set_texel_density(
			self, 
			context,
			bpy.context.scene.texToolsSettings.texel_get_mode,
			bpy.context.scene.texToolsSettings.texel_set_mode,
			bpy.context.scene.texToolsSettings.texel_density
		)
		return {'FINISHED'}



def set_texel_density(self, context, getmode, setmode, density):
	print("Set texel density!")
	
	is_edit = bpy.context.object.mode == 'EDIT'
	is_sync = bpy.context.scene.tool_settings.use_uv_select_sync
	object_faces = utilities_texel.get_selected_object_faces()

	# Warning: No valid input objects
	if len(object_faces) == 0:
		self.report({'ERROR_INVALID_INPUT'}, "No valid meshes or UV maps" )
		return

	if getmode == 'IMAGE':
		# Collect Images / textures
		object_images = {}
		for obj in object_faces:
			image = utilities_texel.get_object_texture_image(obj)
			if image:
				object_images[obj] = image
		
		if len(object_images) == 0:	# Warning: No valid images
			self.report({'ERROR_INVALID_INPUT'}, "No Texture found. Assign Checker map or texture." )
			return
		size = min(image.size[0], image.size[1])
	
	elif getmode == 'SIZE':
		size = min(bpy.context.scene.texToolsSettings.size[0], bpy.context.scene.texToolsSettings.size[1])
	else:
		size = int(getmode)


	for obj in object_faces:
		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.ops.object.select_all(action='DESELECT')
		bpy.context.view_layer.objects.active = obj
		obj.select_set( state = True, view_layer = None)

		# Find image of object
		if getmode == 'IMAGE':
			image = object_images[obj]
		if (getmode == 'IMAGE' and image) or getmode != 'IMAGE':
			bpy.ops.object.mode_set(mode='EDIT')
			bpy.context.scene.tool_settings.use_uv_select_sync = False

			bm = bmesh.from_edit_mesh(obj.data)
			uv_layers = bm.loops.layers.uv.verify()

			# Collect groups of faces to scale together
			group_faces = []
			if is_edit:
				# Collect selected faces as islands
				bm.faces.ensure_lookup_table()
				#bpy.ops.uv.select_all(action='SELECT')
				group_faces = utilities_uv.getSelectionIslands()

			elif setmode == 'ALL':
				# Scale all UV's together
				group_faces = [bm.faces]

			elif setmode == 'ISLAND':
				# Scale each UV island centered
				bpy.ops.mesh.select_all(action='SELECT')
				bpy.ops.uv.select_all(action='SELECT')
				group_faces = utilities_uv.getSelectionIslands()

			print("group_faces {}x".format(len(group_faces)))

			#Store selection
			utilities_uv.selection_store()

			# Set Scale Origin to Island or top left
			#prepivot = bpy.context.space_data.pivot_point
			if setmode == 'ISLAND':
				bpy.context.space_data.pivot_point = 'MEDIAN'
				#bpy.context.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
			else:
				bpy.context.space_data.pivot_point = 'CURSOR'
				#bpy.context.tool_settings.transform_pivot_point = 'CURSOR'
				bpy.ops.uv.cursor_set(location=(0, 1))

			for group in group_faces:
				# Get triangle areas
				sum_area_vt = 0
				sum_area_uv = 0

				for face in group:
					# Decomposed face into triagles to calculate area
					tris = len(face.loops)-2
					if tris <=0:
						continue

					index = None
					area_uv = 0
					area_vt = 0

					for i in range(tris):
						vA = face.loops[0][uv_layers].uv
						if index is None:
							origin = face.loops[0].link_loop_next
						else:
							for loop in face.loops:
								if loop.vert.index == index:
									origin = loop.link_loop_next
									break
						vB = origin[uv_layers].uv
						vC = origin.link_loop_next[uv_layers].uv

						area_uv += mathutils.geometry.area_tri(Vector(vA), Vector(vB), Vector(vC))

						vAr = face.loops[0].vert.co
						vBr = origin.vert.co
						vCr = origin.link_loop_next.vert.co

						area_vt += mathutils.geometry.area_tri(Vector(vAr), Vector(vBr), Vector(vCr))

						index = origin.vert.index
					
					sum_area_vt += math.sqrt( area_vt )
					sum_area_uv += math.sqrt( area_uv ) * size

				# Apply scale to group
				print("scale: {:.2f} {:.2f} {:.2f} ".format(density, sum_area_uv, sum_area_vt))
				scale = 0
				if density > 0 and sum_area_uv > 0 and sum_area_vt > 0:
					scale = density / (sum_area_uv / sum_area_vt)

				# Select Face loops and scale
				bpy.ops.uv.select_all(action='DESELECT')
				bpy.context.scene.tool_settings.uv_select_mode = 'VERTEX'
				for face in group:
					for loop in face.loops:
						loop[uv_layers].select = True

				print("Scale: {} {}x".format(scale, len(group)))
				bpy.ops.transform.resize(value=(scale, scale, 1), use_proportional_edit=False)

			# Restore selection
			utilities_uv.selection_restore()
			#bpy.context.space_data.pivot_point = prepivot

	# Restore selection
	bpy.ops.object.mode_set(mode='OBJECT')
	bpy.ops.object.select_all(action='DESELECT')
	for obj in object_faces:
		obj.select_set( state = True, view_layer = None)
	bpy.context.view_layer.objects.active = list(object_faces.keys())[0]

	# Restore edit mode
	if is_edit:
		bpy.ops.object.mode_set(mode='EDIT')

	# Restore sync mode
	if is_sync:
		bpy.context.scene.tool_settings.use_uv_select_sync = True


bpy.utils.register_class(op)
