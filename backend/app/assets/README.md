# Rigged dancer asset source and licensing

The Story-to-Dance renderer uses `innerscene-female-base-cc0.glb`, a rigged
female base mesh authored by Innerscene Corp. The original GLB is bundled with
its embedded asset metadata intact; that metadata dedicates the model to the
public domain under **CC0 1.0 Universal**
([license text](https://creativecommons.org/publicdomain/zero/1.0/)).
The source metadata identifies `innerscene.com` as the author.

The imported base contains a 71,695-vertex body mesh and a 163-bone armature
with independently weighted fingers, toes, and facial bones. It has no image
textures; the renderer supplies procedural skin shading and creates the teal
and maroon costume, hair, flowers, makeup, and jewelry as animation-compatible
Blender geometry. The existing Story-to-Dance control rig is retargeted to the
base armature. Dance-to-Story does not use or depend on this asset.

Blender 3.6.5 renders the scene and FFmpeg encodes the resulting frames as
H.264 MP4. The model and procedural shading are stylized 3D graphics, not
photorealistic video or expert-validated Bharatanatyam choreography.
