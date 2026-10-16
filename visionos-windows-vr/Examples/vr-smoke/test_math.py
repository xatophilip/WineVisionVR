#!/usr/bin/env python3
"""Execute the actual scene's bounds and tracked CPU projection functions."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[3]
source=Path(__file__).with_name('main.c').read_text()
def function(signature):
 a=source.index(signature);b=source.index('{',a);end=b+1;depth=1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[a:end]
code='''#include <assert.h>
#include <math.h>
#include <string.h>
#include <openvr_capi.h>
typedef struct {float position[4],color[4];} Vertex;
'''+function('static void vertex(')+'\n'+function('static VRTextureBounds_t makeBounds(')+r'''
int main(void){
 for(int eye=0;eye<2;eye++)for(int inverted=0;inverted<2;inverted++){
  VRTextureBounds_t b=makeBounds(eye,inverted);
  assert(b.uMin==(inverted?eye*.5f:0)&&b.uMax==(inverted?(eye+1)*.5f:1));
  assert(b.vMin==(inverted?1:0)&&b.vMax==(inverted?0:1));
  assert(fabsf(b.uMax-b.uMin)>0&&fabsf(b.vMax-b.vMin)>0);
 }
 TrackedDevicePose_t head={0};for(int n=0;n<3;n++)head.mDeviceToAbsoluteTracking.m[n][n]=1;
 head.mDeviceToAbsoluteTracking.m[0][3]=1;head.mDeviceToAbsoluteTracking.m[1][3]=1.4f;
 const float p[3]={1,1.4f,-2},color[4]={1,0,0,1},frustum[4]={-1,1,-1,1};
 Vertex left,right,inverted;
 vertex(&left,&head,0,p,color,frustum,0);vertex(&right,&head,1,p,color,frustum,0);
 assert(fabsf(left.position[0]-.032f)<1e-6f&&fabsf(right.position[0]+.032f)<1e-6f);
 assert(left.position[1]==0&&left.position[3]==2&&left.position[2]>0&&left.position[2]<left.position[3]);
 float above[3]={1,1.9f,-2};vertex(&left,&head,0,above,color,frustum,0);vertex(&inverted,&head,0,above,color,frustum,1);
 assert(left.position[1]>.49f&&inverted.position[1]==-left.position[1]);
 const float asymmetric[4]={-.8f,1.2f,-.7f,1.1f};
 float upper[3]={1,2.5f,-1},lower[3]={1,.7f,-1};
 vertex(&left,&head,0,upper,color,asymmetric,0);assert(fabsf(left.position[1]/left.position[3]-1)<1e-5f);
 vertex(&left,&head,0,lower,color,asymmetric,0);assert(fabsf(left.position[1]/left.position[3]+1)<1e-5f);
 head.mDeviceToAbsoluteTracking.m[0][3]=1.5f;vertex(&left,&head,0,p,color,frustum,0);assert(left.position[0]<0);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='vr-scene-math-') as work:
 p=Path(work);(p/'test.c').write_text(code)
 subprocess.run(['clang','-std=c11','-fsanitize=address,undefined','-I',str(root/'third-party/openvr/headers'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS: production VR scene stereo bounds, head translation, eye separation, projection/depth and inversion (ASan/UBSan); no Windows/GPU execution')
