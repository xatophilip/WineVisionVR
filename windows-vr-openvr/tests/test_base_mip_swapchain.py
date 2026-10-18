#!/usr/bin/env python3
"""Execute production OC base-mip descriptors/copy methods and OpenXR allocation guards.
Recording D3D/XR boundaries do not execute DXMT, Windows shaders or headset rendering.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--source",required=True,type=Path)
p.add_argument("--build",required=True,type=Path)
p.add_argument("--toolchain",type=Path,help="Pinned LLVM-MinGW root; defaults to AVPPLAY_LLVM_MINGW_ROOT or a MinGW compiler on PATH")
a=p.parse_args()
source=a.source.resolve();build=a.build.resolve()
for protected in [ROOT,source]:
    if build==protected or protected in build.parents:p.error("--build must be outside source/checkout")
toolchain=a.toolchain or (Path(os.environ["AVPPLAY_LLVM_MINGW_ROOT"]) if os.environ.get("AVPPLAY_LLVM_MINGW_ROOT") else None)
if toolchain is None:
    compiler=next((shutil.which(name) for name in ["x86_64-w64-mingw32-clang","aarch64-w64-mingw32-clang","i686-w64-mingw32-clang"] if shutil.which(name)),None)
    if compiler:toolchain=Path(compiler).resolve().parent.parent
if toolchain is None:p.error("Pinned LLVM-MinGW headers required: pass --toolchain or set AVPPLAY_LLVM_MINGW_ROOT")
toolchain=toolchain.resolve()
dxgi_path=next((toolchain/rel for rel in ["generic-w64-mingw32/include/dxgiformat.h","x86_64-w64-mingw32/include/dxgiformat.h"] if (toolchain/rel).is_file()),None)
if dxgi_path is None:p.error("Cannot find dxgiformat.h in toolchain "+str(toolchain)+"; supply the pinned LLVM-MinGW root")
build.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix="base-mip-",dir=build))
tmp=work/"tmp";tmp.mkdir()
env=dict(os.environ,TMPDIR=str(tmp),CLANG_MODULE_CACHE_PATH=str(tmp/"cache"))
rel=Path("OpenOVR/Compositor/dx11compositor.cpp")
original=(source/rel).read_bytes()
target=work/"source"/rel;target.parent.mkdir(parents=True);target.write_bytes(original)
patch=ROOT/"windows-vr-openvr/patches/0012-d3d11-base-mip-swapchain.patch"
check=subprocess.run(["git","apply","--check",str(patch)],cwd=work/"source",capture_output=True,text=True)
if check.returncode:
    reverse=subprocess.run(["git","apply","--reverse","--check",str(patch)],cwd=work/"source",capture_output=True,text=True)
    assert reverse.returncode==0,check.stderr+reverse.stderr
    subprocess.run(["git","apply","--reverse",str(patch)],cwd=work/"source",check=True)
legacy=target.read_text()
subprocess.run(["git","apply",str(patch)],cwd=work/"source",check=True)
text=target.read_text()
xrpath=ROOT/"windows-vr-openxr/src/WindowsVROpenXR.cpp";xr=xrpath.read_text()
def function(text,signature):
    start=text.index(signature);brace=text.index("{",start);end=brace+1;depth=1
    while depth:depth+=(text[end]=="{")-(text[end]=="}");end+=1
    return text[start:end]
header=(source/"OpenOVR/Compositor/WVRTextureBounds.h").read_text()
dxgi=dxgi_path.read_text()
format_constants="\n".join("constexpr int "+name+"="+str(int(value,0))+";" for name,value in re.findall(r"\b(DXGI_FORMAT_[A-Z0-9_]+)\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)",dxgi) if name!="DXGI_FORMAT_FORCE_UINT")
assert "DXGI_FORMAT_R8G8B8A8_UNORM_SRGB=29;" in format_constants

shell=r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <vector>
using UINT=unsigned;using UINT16=uint16_t;using HRESULT=int;using DXGI_FORMAT=int;using XrResult=int;using XruEye=int;
""" + format_constants + r"""
constexpr int XR_SUCCESS=0,XR_ERROR_HANDLE_INVALID=-12,XR_ERROR_VALIDATION_FAILURE=-1,XR_ERROR_FEATURE_UNSUPPORTED=-8,
 XR_ERROR_SWAPCHAIN_FORMAT_UNSUPPORTED=-26,XR_ERROR_RUNTIME_FAILURE=-2,XR_ERROR_SWAPCHAIN_RECT_INVALID=-25,XR_TIMEOUT_EXPIRED=1;
constexpr int XR_TYPE_SWAPCHAIN_CREATE_INFO=1,XR_TYPE_SWAPCHAIN_IMAGE_D3D11_KHR=2,
 XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO=3,XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO=4,XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO=5;
using XrSwapchainCreateFlags=uint64_t;using XrSwapchainUsageFlags=uint64_t;
constexpr uint64_t XR_SWAPCHAIN_CREATE_STATIC_IMAGE_BIT=1,XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT=1,
 XR_SWAPCHAIN_USAGE_SAMPLED_BIT=32,XR_SWAPCHAIN_USAGE_TRANSFER_SRC_BIT=8,XR_SWAPCHAIN_USAGE_TRANSFER_DST_BIT=16,
 XR_SWAPCHAIN_USAGE_MUTABLE_FORMAT_BIT=64,XR_SWAPCHAIN_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT=2;
constexpr unsigned D3D11_USAGE_DEFAULT=0,D3D11_BIND_RENDER_TARGET=32,D3D11_BIND_SHADER_RESOURCE=8,D3D11_BIND_DEPTH_STENCIL=64,
 D3D11_SRV_DIMENSION_TEXTURE2D=1,D3D11_MAP_WRITE_DISCARD=1,D3D11_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP=1;
constexpr int D3D12_HEAP_TYPE_DEFAULT=0,D3D12_RESOURCE_DIMENSION_TEXTURE2D=0,D3D12_TEXTURE_LAYOUT_UNKNOWN=0,
 D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL=1,D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET=2,D3D12_HEAP_FLAG_NONE=0,D3D12_RESOURCE_STATE_COMMON=0;
#define FAILED(x) ((x)<0)
#define XR_SUCCEEDED(x) ((x)>=0)
#define OOVR_LOG(...) ((void)0)
#define OOVR_LOGF(...) ((void)0)
#define OOVR_ABORTF(...) throw std::runtime_error("OC abort")
#define OOVR_FALSE_ABORT(x) do {if(!(x))throw std::runtime_error("OC false");}while(0)
#define OOVR_FAILED_XR_ABORT(x) do {auto r=(x);if(r<0)throw std::runtime_error("OC XR "+std::to_string(r));}while(0)
#define OOVR_FAILED_DX_ABORT(x) do {if(FAILED(x))throw std::runtime_error("OC DX");}while(0)
#define IID_PPV_ARGS(p) p
struct Sample {UINT Count=1,Quality=0;};
struct D3D11_TEXTURE2D_DESC {UINT Width=0,Height=0,MipLevels=1,ArraySize=1;DXGI_FORMAT Format=29;Sample SampleDesc;UINT Usage=0,BindFlags=40,CPUAccessFlags=0,MiscFlags=0;};
UINT D3D11CalcSubresource(UINT mip,UINT slice,UINT levels){return mip+slice*levels;}
struct Texture {D3D11_TEXTURE2D_DESC desc;int releases=0;void GetDesc(D3D11_TEXTURE2D_DESC*out){*out=desc;}void Release(){releases++;}};
using ID3D11Texture2D=Texture;
struct View {void Release(){}};
using ID3D11ShaderResourceView=View;
struct ID3D11CommandList{void Release(){}};
struct D3D11_BOX{UINT left,right,top,bottom,front,back;};
struct D3D11_VIEWPORT{float a,b,c,d,e,f;};
struct D3D11_SHADER_RESOURCE_VIEW_DESC {DXGI_FORMAT Format;UINT ViewDimension;struct {UINT MostDetailedMip=0,MipLevels=0;}Texture2D;};
struct D3D11_MAPPED_SUBRESOURCE{void*pData;};
struct Copy {Texture*source;UINT sub;bool resolve;};
struct Context {
 std::vector<Copy>copies;UINT srvMipCount=0;char data[64]{};
 void CopySubresourceRegion(Texture*,UINT,UINT,UINT,UINT,Texture*src,UINT sub,const D3D11_BOX*){copies.push_back({src,sub,false});}
 void ResolveSubresource(Texture*,UINT,Texture*src,UINT sub,DXGI_FORMAT){copies.push_back({src,sub,true});}
 int Map(void*,UINT,UINT,UINT,D3D11_MAPPED_SUBRESOURCE*out){out->pData=data;return 0;}
 template<class...T>void Unmap(T...){}
 template<class...T>void RSSetViewports(T...){}
 template<class...T>void RSSetState(T...){}
 template<class...T>void OMSetRenderTargets(T...){}
 template<class...T>void VSSetShader(T...){}
 template<class...T>void VSSetConstantBuffers(T...){}
 template<class...T>void PSSetShader(T...){}
 template<class...T>void PSSetShaderResources(T...){}
 template<class...T>void PSSetSamplers(T...){}
 template<class...T>void IASetPrimitiveTopology(T...){}
 template<class...T>void Draw(T...){}
 int FinishCommandList(bool,ID3D11CommandList**out){static ID3D11CommandList c;*out=&c;return 0;}
 template<class...T>void ExecuteCommandList(T...){}
};
constexpr bool FALSE=false,TRUE=true;
struct D3D12_HEAP_PROPERTIES{int Type,CreationNodeMask,VisibleNodeMask;};
struct D3D12_RESOURCE_DESC{int Dimension;uint64_t Width;UINT Height;uint16_t DepthOrArraySize;UINT MipLevels;DXGI_FORMAT Format;Sample SampleDesc;int Layout,Flags;};
struct Device {
 std::vector<std::unique_ptr<Texture>>all;int calls=0,failAt=0;
 int CreateTexture2D(const D3D11_TEXTURE2D_DESC*d,void*,Texture**out){if(++calls==failAt)return -1;all.push_back(std::make_unique<Texture>());*out=all.back().get();(*out)->desc=*d;return 0;}
 int CreateShaderResourceView(Texture*,D3D11_SHADER_RESOURCE_VIEW_DESC*d,View**out){static View v;assert(d->Texture2D.MipLevels==1);*out=&v;return 0;}
 int CreateCommittedResource(D3D12_HEAP_PROPERTIES*,int,D3D12_RESOURCE_DESC*,int,void*,Texture**){return -1;}
};
struct WVRDXMTTargetInfoV1{uint64_t generation=1;UINT width[2]{1920,1920},height[2]{1792,1792},pixelFormat[2]{71,71};};
struct Instance{WVRDXMTTargetInfoV1 targets;bool depthEnabled=false;};
struct Session;struct Swapchain;
using XrSession=Session*;using XrSwapchain=Swapchain*;
constexpr XrSwapchain XR_NULL_HANDLE=nullptr;
struct XrSwapchainCreateInfo {int type;const void*next=nullptr;uint64_t createFlags=0,usageFlags=0;int64_t format=0;UINT sampleCount=0,width=0,height=0,faceCount=0,arraySize=0,mipCount=0;};
struct Image{Texture*texture11=nullptr,*resource12=nullptr;};
struct Session{Instance*instance;Device*device,*device12;bool d3d12=false;void*dxmtExt3=reinterpret_cast<void*>(1);std::vector<Swapchain*>swapchains;};
struct Swapchain{Session*session;XrSwapchainCreateInfo info;uint64_t targetGeneration;std::vector<Image>images;};
std::mutex g_mutex;std::vector<std::unique_ptr<Swapchain>>g_swapchains;
constexpr unsigned kImageCount=3;
Session*GetSession(Session*s){return s;}
int GetSessionTargets(Session*s,WVRDXMTTargetInfoV1*out){*out=s->instance->targets;return 0;}
void RegisterHandle(Swapchain*){}
template<class T>T WVRHandleFromPointer(Swapchain*p){return p;}
""" + function(xr,"DXGI_FORMAT FormatForMetal(")+"\n"+function(xr,"XrResult XRAPI_CALL CreateSwapchainImpl(").replace("XRAPI_CALL ","")+r"""
int CreateCalls=0;XrSwapchainCreateInfo LastRequest{};
int xrCreateSwapchain(Session*s,const XrSwapchainCreateInfo*d,Swapchain**out){++CreateCalls;LastRequest=*d;return CreateSwapchainImpl(s,d,out);}
int xrDestroySwapchain(Swapchain*){return 0;}
struct XrSwapchainImageBaseHeader {int type;};
using XrBaseInStructure=XrSwapchainImageBaseHeader;
struct XrSwapchainImageD3D11KHR {int type;Texture*texture=nullptr;};
int xrEnumerateSwapchainImages(Swapchain*s,UINT cap,UINT*count,XrSwapchainImageBaseHeader*out){
 *count=s->images.size();if(cap){auto*images=reinterpret_cast<XrSwapchainImageD3D11KHR*>(out);for(UINT i=0;i<*count;i++)images[i].texture=s->images[i].texture11;}return 0;
}
struct XrSwapchainImageAcquireInfo{int type;};
struct XrSwapchainImageWaitInfo{int type;int64_t timeout=0;};
struct XrSwapchainImageReleaseInfo{int type;};
int xrAcquireSwapchainImage(Swapchain*,XrSwapchainImageAcquireInfo*,UINT*out){*out=0;return 0;}
int xrWaitSwapchainImage(Swapchain*,XrSwapchainImageWaitInfo*){return 0;}
int xrReleaseSwapchainImage(Swapchain*,XrSwapchainImageReleaseInfo*){return 0;}
View* d3d_make_rtv(Device*,XrSwapchainImageBaseHeader&,int){static View v;return &v;}
namespace vr {enum EColorSpace{ColorSpace_Auto,ColorSpace_Linear,ColorSpace_Gamma};enum EVRSubmitFlags{Submit_Default};
struct VRTextureBounds_t{float uMin,uMax,vMin,vMax;};struct Texture_t{void*handle;EColorSpace eColorSpace=ColorSpace_Auto;};}
struct SessionRef{Session*s;Session*get(){return s;}};
struct DX11Compositor{
 struct DxgiFormatInfo{DXGI_FORMAT srgb,linear,typeless;int bpp,bpc,channels;};
 Device*device;Context*context,*boundsContext;SessionRef xr_session;
 XrSwapchain chain=nullptr;XrSwapchainCreateInfo createInfo{};int createInfoFormat=0;
 D3D11_TEXTURE2D_DESC sourceShape;
 std::vector<View*>swapchain_rtvs;std::vector<Texture*>resolvedMSAATextures;
 std::vector<XrSwapchainImageD3D11KHR>imagesHandles;
 View*quad_texture_view=nullptr;Texture*cached_srv_source=nullptr;
 void*boundsUniform=nullptr,*fs_vshader=nullptr,*fs_pshader=nullptr,*quad_sampleState=nullptr;
 bool CheckChainCompatible(D3D11_TEXTURE2D_DESC&,vr::EColorSpace);
 bool GetFormatInfo(DXGI_FORMAT,DxgiFormatInfo&);
 void CheckCreateSwapChain(const vr::Texture_t*,const vr::VRTextureBounds_t*,bool);
 void OldCheckCreateSwapChain(const vr::Texture_t*,const vr::VRTextureBounds_t*,bool);
 void CopyToSwapchain(const vr::Texture_t*,const vr::VRTextureBounds_t*,std::optional<XruEye>,vr::EVRSubmitFlags);
};
"""
shell="#define XRAPI_CALL\n"+shell
code=shell+"\n"+header+"\n"+"\n".join(function(text,sig) for sig in [
 "bool DX11Compositor::GetFormatInfo(","bool DX11Compositor::CheckChainCompatible(","void DX11Compositor::CheckCreateSwapChain(","void DX11Compositor::CopyToSwapchain("])+ "\n" + function(legacy,"void DX11Compositor::CheckCreateSwapChain(").replace("DX11Compositor::CheckCreateSwapChain(","DX11Compositor::OldCheckCreateSwapChain(",1)
driver=r"""
int main(){
 Instance instance;Device device;Session session{&instance,&device,&device};Context context;
 auto make=[&]{DX11Compositor c;c.device=&device;c.context=c.boundsContext=&context;c.xr_session={&session};return c;};
 auto source=[&](UINT mips,UINT arrays=1,UINT samples=1){Texture t;t.desc.Width=1476;t.desc.Height=800;t.desc.Format=29;t.desc.BindFlags=8;t.desc.MipLevels=mips;t.desc.ArraySize=arrays;t.desc.SampleDesc.Count=samples;return t;};
 auto oldTexture=source(11);vr::Texture_t oldInput{&oldTexture};auto oldCompositor=make();
 bool oldRejected=false;
 try{oldCompositor.OldCheckCreateSwapChain(&oldInput,nullptr,false);}catch(const std::runtime_error&){oldRejected=true;}
 assert(oldRejected&&LastRequest.mipCount==11&&LastRequest.format==29&&LastRequest.usageFlags==49);
 puts("PASS exact old OC descriptor requests11mips and actual retained OpenXR guard rejects-8");
 // The following runtime checks isolate that exact observed feature predicate:
 // source mip chain fails the retained runtime guard; bind8/format29 alone do not.
 XrSwapchainCreateInfo bad{XR_TYPE_SWAPCHAIN_CREATE_INFO};bad.width=1476;bad.height=800;bad.format=29;
 bad.faceCount=bad.arraySize=bad.sampleCount=1;bad.mipCount=11;bad.usageFlags=49;
 Swapchain*out=nullptr;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_ERROR_FEATURE_UNSUPPORTED);
 bad.mipCount=1;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_SUCCESS);
 for(UINT mips:{0u,1u,2u,11u}){
  auto texture=source(mips);auto original=texture.desc;vr::Texture_t input{&texture};auto c=make();
  vr::VRTextureBounds_t inverted{0,1,1,0};
  c.CopyToSwapchain(&input,&inverted,0,vr::Submit_Default);
  assert(LastRequest.mipCount==1&&LastRequest.width==1476&&LastRequest.height==800&&LastRequest.format==29);
  assert(LastRequest.usageFlags==49&&texture.desc.MipLevels==original.MipLevels&&texture.desc.BindFlags==8);
  int calls=CreateCalls;c.CopyToSwapchain(&input,&inverted,0,vr::Submit_Default);
  assert(CreateCalls==calls); // No per-frame recreation from source/destination mip mismatch.
  texture.desc.MipLevels=3;c.CopyToSwapchain(&input,&inverted,0,vr::Submit_Default);assert(CreateCalls==calls+1);
 }
 puts("PASS actual descriptor/copy/cache: source mips0/1/2/11 -> one base image; exact1476x800 SRGB bind8 source unchanged; mip changes recreate once");
 // No-bounds and shader-bounds paths both select mip0 of the correct array slice.
 for(bool bounds:{false,true})for(UINT samples:{1u,4u})for(UINT levels:{0u,1u,4u}){
  auto texture=source(levels,2,samples);vr::Texture_t input{&texture};auto c=make();context.copies.clear();
  vr::VRTextureBounds_t inverted{0,1,1,0};
  c.CopyToSwapchain(&input,bounds?&inverted:nullptr,1,vr::Submit_Default);
  assert(!context.copies.empty()&&context.copies.front().source==&texture);
  assert(context.copies.front().sub==std::max(1u,levels));
  assert(context.copies.front().resolve==(samples>1));
 }
 puts("PASS actual array/MSAA copy methods: correct base-mip source slice with/without inverted bounds");
 // Baseline double-wide geometry and cubemap rejection remain unchanged.
 auto texture=source(1);texture.desc.Width=3840;texture.desc.Height=1792;texture.desc.Format=27;texture.desc.BindFlags=40;
 vr::Texture_t input{&texture};auto c=make();c.CheckCreateSwapChain(&input,nullptr,false);
 assert(LastRequest.width==3840&&LastRequest.height==1792&&LastRequest.format==29&&LastRequest.mipCount==1);
 texture.desc.MipLevels=5;c=make();bool rejected=false;
 try{c.CheckCreateSwapChain(&input,nullptr,true);}catch(const std::runtime_error&){rejected=true;}
 assert(rejected&&LastRequest.faceCount==6&&LastRequest.mipCount==5);
 puts("PASS baseline full-size scene, preserved cube path/rejection; no format/dimension/runtime guard widening");
 // Actual production runtime retains shape bounds and allocation rollback.
 bad.mipCount=2;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_ERROR_FEATURE_UNSUPPORTED);
 bad.mipCount=1;bad.width=0;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_ERROR_SWAPCHAIN_RECT_INVALID);
 bad.width=5372;bad.height=2507;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_ERROR_SWAPCHAIN_RECT_INVALID);
 bad.width=1476;bad.height=800;bad.format=28;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_ERROR_SWAPCHAIN_FORMAT_UNSUPPORTED);
 bad.format=29;auto allocations=device.all.size();auto registered=g_swapchains.size();
 device.failAt=device.calls+2;assert(CreateSwapchainImpl(&session,&bad,&out)==XR_ERROR_RUNTIME_FAILURE);
 assert(device.all.size()==allocations+1&&device.all.back()->releases==1&&g_swapchains.size()==registered);
 puts("PASS actual OpenXR format/mip/size guards and partial allocation cleanup");
}
"""
unit=work/"production.cpp";unit.write_text(code+"\n"+driver)
command=["xcrun","--sdk","macosx","clang++","-std=c++20","-O1","-g","-fsanitize=address,undefined","-fno-omit-frame-pointer",str(unit),"-o",str(work/"probe")]
compiled=subprocess.run(command,env=env,capture_output=True,text=True,timeout=120)
(work/"compile.log").write_text(compiled.stdout+compiled.stderr);compiled.check_returncode()
# Fake COM resource ownership is retained until process teardown; production
# rollback Release calls are asserted explicitly rather than leak-modelled.
run=subprocess.run([str(work/"probe")],env=dict(env,ASAN_OPTIONS="detect_leaks=0"),capture_output=True,text=True,timeout=30)
(work/"execution.log").write_text(run.stdout+run.stderr);run.check_returncode()
assert (source/rel).read_bytes()==original
assert "info->mipCount!=1" in xr
assert "info->layerCount!=1" in function(xr,"XrResult XRAPI_CALL EndFrame(")
assert "layer->type!=XR_TYPE_COMPOSITION_LAYER_PROJECTION" in function(xr,"XrResult XRAPI_CALL EndFrame(")
report={"passed":True,"scope":__doc__,"command":command,"stdout":run.stdout,"source":str(source/rel),"sourceBeforeSha256":hashlib.sha256(original).hexdigest(),"patchedSourceSha256":hashlib.sha256(text.encode()).hexdigest(),"legacyAdapterSourceSha256":hashlib.sha256(legacy.encode()).hexdigest(),"patchSha256":hashlib.sha256(patch.read_bytes()).hexdigest(),"testSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"runtimeSourceSha256":hashlib.sha256(xr.encode()).hexdigest(),"dxgiHeaderSha256":hashlib.sha256(dxgi.encode()).hexdigest(),"dxgiHeader":str(dxgi_path),"toolchain":str(toolchain),"probeSha256":hashlib.sha256(unit.read_bytes()).hexdigest(),"originalSourceUnchanged":True,"limitations":["Recording D3D/XR allocation/copy boundaries; no Windows DXBC/DXMT/headset execution.","Actual failing device descriptor MipLevels was not logged; mip cause is deductive from the sole remaining unsupported feature predicate.","Runtime still accepts one projection layer only; visible OpenVR quad overlays remain a separate known unsupported composition path."]}
(work/"result.json").write_text(json.dumps(report,indent=2)+"\n")
print(run.stdout,end="");print("Receipt:",work/"result.json")
