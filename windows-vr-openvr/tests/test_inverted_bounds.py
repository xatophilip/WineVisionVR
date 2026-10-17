#!/usr/bin/env python3
"""Test patched production bounds/viewport code and GPU UV crop mapping.

The Mac GPU test compiles the production HLSL mapping function unchanged as
MSL. It does not execute the Windows DXBC shader or prove guest rendering.
"""
import argparse
from pathlib import Path
import os
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path, help='OpenComposite overlay with patch 0008 applied')
p.add_argument('--build', required=True, type=Path)
a = p.parse_args()
source = a.source.resolve() / 'OpenOVR/Compositor'
build = a.build.resolve()
build.mkdir(parents=True, exist_ok=True)

def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

compositor = (source / 'compositor.cpp').read_text()
dx11 = (source / 'dx11compositor.cpp').read_text()
header = (source / 'WVRTextureBounds.h').read_text()
# These are the production method bodies, with only the platform types stubbed.
code = '''#include <cassert>
#include <cmath>
#include <limits>
#include <cstdint>
#include <optional>
#include "WVRTextureBounds.h"
namespace vr { struct VRTextureBounds_t {float uMin,uMax,vMin,vMax;}; struct Texture_t {}; enum EVRSubmitFlags {Submit_Default}; }
using XruEye=int;
struct XrRect2Di {struct {int32_t x,y;} offset; struct {int32_t width,height;} extent;};
struct XrExtent2Di {int32_t width,height;};
struct XrSwapchainSubImage {int swapchain;uint32_t imageArrayIndex;XrRect2Di imageRect;};
struct Config {bool InvertUsingShaders() const {return false;}} oovr_global_configuration;
struct Compositor {
 virtual bool InvertBoundsInCompositor(const vr::VRTextureBounds_t*) const;
 void Invoke(const vr::Texture_t*,const vr::VRTextureBounds_t*,XrSwapchainSubImage&,std::optional<XruEye>,vr::EVRSubmitFlags);
 bool CalculateViewport(const vr::VRTextureBounds_t*,int32_t,int32_t,bool,XrRect2Di&);
 bool depthValid=false;unsigned depthCopies=0;
 void CopyDepth(const vr::Texture_t*,const vr::VRTextureBounds_t*,std::optional<XruEye>,vr::EVRSubmitFlags){++depthCopies;}
 bool copiedBounds=false; const vr::VRTextureBounds_t* copied=nullptr;
 void CopyToSwapchain(const vr::Texture_t*,const vr::VRTextureBounds_t* b,std::optional<XruEye>,vr::EVRSubmitFlags){copiedBounds=b!=nullptr;copied=b;}
 int GetSwapChain(){return 1;}
 XrExtent2Di GetSrcSize(){return copiedBounds ? XrExtent2Di{1920,1792}:XrExtent2Di{3840,1792};}
};
struct DX11Compositor:Compositor {bool InvertBoundsInCompositor(const vr::VRTextureBounds_t*) const override;};
'''
for text, signature in [(compositor, 'bool Compositor::InvertBoundsInCompositor'),
                        (compositor, 'void Compositor::Invoke'),
                        (compositor, 'bool Compositor::CalculateViewport'),
                        (dx11, 'bool DX11Compositor::InvertBoundsInCompositor')]:
    code += function(text, signature) + '\n'
code += '''int main(){
 for(int eye=0;eye<2;++eye){
  vr::VRTextureBounds_t b{eye*.5f,(eye+1)*.5f,1,0};
  WVRBoundsUniform uv{};assert(WVRMakeBoundsUniform(b.uMin,b.uMax,b.vMin,b.vMax,uv));
  assert(uv.originX==eye*.5f&&uv.originY==1&&uv.extentX==.5f&&uv.extentY==-1);
  DX11Compositor c;XrSwapchainSubImage image{};c.Invoke(nullptr,&b,image,eye,vr::Submit_Default);
  assert(c.copiedBounds&&image.imageRect.offset.x==0&&image.imageRect.offset.y==0);
  assert(c.depthCopies==1&&!c.depthValid);
  assert(image.imageRect.extent.width==1920&&image.imageRect.extent.height==1792);
  Compositor old;XrRect2Di negative{};old.CalculateViewport(&b,3840,1792,true,negative);
  assert(negative.extent.height==-1792); // Exact observed failure, negative control.
  b.vMin=0;b.vMax=1;c.Invoke(nullptr,&b,image,eye,vr::Submit_Default);
  assert(!c.copiedBounds&&image.imageRect.offset.x==eye*1920&&image.imageRect.offset.y==0);
  assert(image.imageRect.extent.width==1920&&image.imageRect.extent.height==1792);
 }
 struct Desc {int Width=3840,Height=1792,ArraySize=1,MipLevels=1,Format=27;struct {int Count=1,Quality=0;} SampleDesc;} base,changed;
 assert(WVRSameSourceShape(base,changed));
 changed.ArraySize=2;assert(!WVRSameSourceShape(base,changed));changed=base;
 changed.SampleDesc.Count=4;assert(!WVRSameSourceShape(base,changed));changed=base;
 changed.Width=7680;assert(!WVRSameSourceShape(base,changed));changed=base;
 changed.MipLevels=2;assert(!WVRSameSourceShape(base,changed));changed=base;
 changed.SampleDesc.Quality=1;assert(!WVRSameSourceShape(base,changed));
 WVRBoundsUniform uv{};
 assert(!WVRMakeBoundsUniform(0,0,0,1,uv));
 assert(!WVRMakeBoundsUniform(-.1f,.5f,1,0,uv));
 assert(!WVRMakeBoundsUniform(0,1,std::numeric_limits<float>::quiet_NaN(),0,uv));
}
'''
(build / 'mapping.cpp').write_text(code)
# The UV helper is a language-compatible production shader function: no
# rewriting of its arithmetic or replacement implementation in the GPU probe.
shader = function(dx11, 'float2 wvr_map_bounds')
metal = '''#include <metal_stdlib>
using namespace metal;
''' + shader + '''
kernel void crop(texture2d<float,access::sample> source [[texture(0)]],
 texture2d<float,access::write> destination [[texture(1)]],
 constant float4& bounds [[buffer(0)]], uint2 p [[thread_position_in_grid]]) {
 constexpr sampler s(coord::normalized, address::clamp_to_edge, filter::nearest);
 float2 uv=(float2(p)+0.5f)/float2(destination.get_width(),destination.get_height());
 destination.write(source.sample(s,wvr_map_bounds(uv,bounds)),p);
}
'''
(build / 'mapping.metal').write_text(metal)
probe = '''#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <cassert>
#include <cstdio>
#include "WVRTextureBounds.h"
int main(int argc,char**argv){@autoreleasepool{
 id<MTLDevice> d=MTLCreateSystemDefaultDevice();assert(d);
 NSError*error=nil;NSString*s=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];
 id<MTLLibrary> lib=[d newLibraryWithSource:s options:nil error:&error];if(error)fprintf(stderr,"%s\\n",error.localizedDescription.UTF8String);assert(lib);
 id<MTLComputePipelineState> pipe=[d newComputePipelineStateWithFunction:[lib newFunctionWithName:@"crop"] error:&error];assert(pipe);
 id<MTLCommandQueue> q=[d newCommandQueue];
 MTLTextureDescriptor*desc=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:8 height:4 mipmapped:NO];
 desc.storageMode=MTLStorageModeShared;desc.usage=MTLTextureUsageShaderRead;
 id<MTLTexture> src=[d newTextureWithDescriptor:desc];unsigned char pixels[128]{};
 for(int y=0;y<4;++y)for(int x=0;x<8;++x){int o=(y*8+x)*4;pixels[o+(x<4?0:2)]=16+y*32;pixels[o+1]=x*16;pixels[o+3]=255;}
 [src replaceRegion:MTLRegionMake2D(0,0,8,4) mipmapLevel:0 withBytes:pixels bytesPerRow:32];
 desc.width=4;desc.usage=MTLTextureUsageShaderWrite;
 for(int eye=0;eye<2;++eye){
  id<MTLTexture> dst=[d newTextureWithDescriptor:desc];WVRBoundsUniform uv{};
  assert(WVRMakeBoundsUniform(eye*.5f,(eye+1)*.5f,1,0,uv));
  id<MTLCommandBuffer> c=[q commandBuffer];id<MTLComputeCommandEncoder> e=[c computeCommandEncoder];
  [e setComputePipelineState:pipe];[e setTexture:src atIndex:0];[e setTexture:dst atIndex:1];[e setBytes:&uv length:sizeof(uv) atIndex:0];
  [e dispatchThreads:MTLSizeMake(4,4,1) threadsPerThreadgroup:MTLSizeMake(4,4,1)];[e endEncoding];[c commit];[c waitUntilCompleted];assert(c.status==MTLCommandBufferStatusCompleted);
  unsigned char out[64];[dst getBytes:out bytesPerRow:16 fromRegion:MTLRegionMake2D(0,0,4,4) mipmapLevel:0];
  for(int y=0;y<4;++y)for(int x=0;x<4;++x)for(int k=0;k<4;++k)assert(out[(y*4+x)*4+k]==pixels[((3-y)*8+eye*4+x)*4+k]);
 }
 puts("PASS: GPU samples the correct eye and vertically inverted rows (32 RGBA pixels)");
}}
'''
(build / 'gpu.mm').write_text(probe)
clang = ['xcrun', '--sdk', 'macosx', 'clang++', '-std=c++20', '-O2', '-I', str(source)]
checks = [('mapping-build', clang + ['-fsanitize=address,undefined', str(build/'mapping.cpp'), '-o', str(build/'mapping')]),
          ('mapping', [str(build/'mapping')]),
          ('gpu-build', clang + ['-fobjc-arc', str(build/'gpu.mm'), '-framework', 'Foundation', '-framework', 'Metal', '-o', str(build/'gpu')]),
          ('gpu', [str(build/'gpu'), str(build/'mapping.metal')])]
for name, command in checks:
    with (build/(name+'.log')).open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    print(name+': PASS', flush=True)
print('PASS: production viewport/UV mapping and Mac GPU crop; Windows DXBC execution remains untested')
