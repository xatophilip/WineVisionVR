// Actual production bridge and real Metal events, with deliberately delayed producers.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "WindowsVRCompositorBridge.h"
#include <cstdio>
#include <cstdlib>
static void require(bool value, const char *message) {
    if (!value) { std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1); }
    std::printf("PASS: %s\n",message);
}
int main() { @autoreleasepool {
    auto device=MTLCreateSystemDefaultDevice();require(device!=nil,"real Metal device");
    require(wvr_compositor_bind_metal_device_v1((__bridge void*)device)==0,"bind production bridge");
    require(wvr_compositor_publish_targets_v1(16,16,MTLPixelFormatRGBA8Unorm,16,16,MTLPixelFormatRGBA8Unorm)==0,"publish targets");
    WVRRenderTargetInfoV1 targets{};targets.structSize=sizeof(targets);require(wvr_compositor_copy_targets_v1(&targets)==0,"read generation");
    auto descriptor=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:16 height:16 mipmapped:NO];
    auto left=[device newTextureWithDescriptor:descriptor],right=[device newTextureWithDescriptor:descriptor];
    auto ready=[device newSharedEvent];auto queue=[device newCommandQueue];
    auto signal=[&](uint64_t value) {auto buffer=[queue commandBuffer];[buffer encodeSignalEvent:ready value:value];[buffer commit];[buffer waitUntilCompleted];require(buffer.status==MTLCommandBufferStatusCompleted,"GPU advances producer fence");};
    WVRSubmitStereoFrameV2 frame{};frame.abiVersion=WVR_COMPOSITOR_ABI_VERSION_V2;frame.structSize=sizeof(frame);frame.targetGeneration=targets.generation;
    frame.leftTexture=(__bridge void*)left;frame.rightTexture=(__bridge void*)right;frame.producerReadyEvent=(__bridge void*)ready;
    frame.leftWidth=frame.leftHeight=frame.rightWidth=frame.rightHeight=16;
    uint64_t ticket=0;
    auto submit=[&](uint64_t id) {frame.producerFrameID=id;frame.producerReadyValue=id;return wvr_compositor_submit_stereo_frame_v2(&frame,&ticket);};
    auto acquire=[&](WVRAcquiredStereoFrameV2 &out) {out={};out.structSize=sizeof(out);return wvr_compositor_acquire_latest_stereo_frame_v2(&out);};
    // A producer completes more than three submissions behind the CPU. The old
    // three-slot queue evicted frame 1 here and could never acquire ready work.
    for(uint64_t id=1;id<=4;++id)require(submit(id)==0,"queue four unfinished producer frames");
    WVRAcquiredStereoFrameV2 acquired{};
    require(acquire(acquired)==WVRCompositorStatusNoFrameAvailable,"never expose unfinished GPU work");
    signal(1);
    require(acquire(acquired)==0 && acquired.producerFrameID==1,"delayed frame survives fourth submission and becomes acquirable");
    require(acquired.leftTexture==frame.leftTexture && acquired.rightTexture==frame.rightTexture,"acquired textures retain ownership");
    wvr_compositor_release_acquired_frame_v1(acquired.lease);
    for(uint64_t id=5;id<=7;++id)require(submit(id)==0,"retain six pending frames within existing ticket window");
    const uint64_t lastAccepted=ticket;ticket=0x12345678;
    require(submit(8)==WVRCompositorStatusNoFrameAvailable && ticket==0x12345678,"full six-ticket window rejects without allocating a ticket");
    WVRCompositorStatsV1 stats{};stats.structSize=sizeof(stats);require(wvr_compositor_copy_stats_v1(&stats)==0 && stats.queuedFrames==6,"pending queue remains bounded at six");
    void *opaque=wvr_compositor_copy_consumer_event_v1();auto consumer=(__bridge id<MTLSharedEvent>)opaque;
    require(consumer.signaledValue==1,"pending frames do not advance consumer completion");
    signal(7);
    require(acquire(acquired)==0 && acquired.producerFrameID==7,"recover latest ready frame after backpressure");
    require(consumer.signaledValue==lastAccepted-1,"skipped tickets retire but acquired lease remains protected");
    wvr_compositor_release_acquired_frame_v1(acquired.lease);
    require(consumer.signaledValue==lastAccepted,"lease completion advances monotonic consumer fence");
    // Keep two acquired leases outstanding and retire them out of order.
    signal(20);require(submit(8)==0 && acquire(acquired)==0,"acquire first protected lease");void *lease8=acquired.lease;
    require(submit(9)==0 && acquire(acquired)==0,"acquire second protected lease");void *lease9=acquired.lease;
    wvr_compositor_release_acquired_frame_v1(lease9);require(consumer.signaledValue==7,"out-of-order release cannot pass older lease");
    wvr_compositor_release_acquired_frame_v1(lease8);require(consumer.signaledValue==9,"closing completion gap retires both leases");
    // Pause invalidates queued targets, but does not invalidate acquired textures.
    require(submit(10)==0 && acquire(acquired)==0,"acquire lease before pause");
    require(submit(11)==0,"queue frame before pause");wvr_compositor_pause_v1();
    require(acquired.leftTexture==(__bridge void*)left && [(__bridge id<MTLTexture>)acquired.leftTexture width]==16,"lease survives pause");
    WVRAcquiredStereoFrameV2 paused{};require(acquire(paused)==WVRCompositorStatusNoFrameAvailable,"pause clears queued work");
    require(consumer.signaledValue==9,"pause cannot retire acquired lease early");
    wvr_compositor_release_acquired_frame_v1(acquired.lease);require(consumer.signaledValue==11,"pause and lease completion close ticket window");
    require(submit(12)==WVRCompositorStatusIncompatibleTexture,"paused stale generation remains rejected");
    require(wvr_compositor_publish_targets_v1(16,16,MTLPixelFormatRGBA8Unorm,16,16,MTLPixelFormatRGBA8Unorm)==0,"resume targets");
    require(wvr_compositor_copy_targets_v1(&targets)==0,"read resumed generation");
    // V1 shares the same bounded queue and must preserve delayed producers too.
    auto readyV1=[device newSharedEvent];WVRSubmitStereoFrameV1 legacy{};legacy.abiVersion=WVR_COMPOSITOR_ABI_VERSION;legacy.structSize=sizeof(legacy);
    legacy.leftTexture=(__bridge void*)left;legacy.rightTexture=(__bridge void*)right;legacy.producerReadyEvent=(__bridge void*)readyV1;
    for(uint64_t id=1;id<=6;++id){legacy.producerFrameID=id;legacy.producerReadyValue=id;require(wvr_compositor_submit_stereo_frame_for_generation_v1(&legacy,targets.generation,&ticket)==0,"V1 retains six unfinished frames");}
    require(wvr_compositor_submit_stereo_frame_for_generation_v1(&legacy,targets.generation,&ticket)==WVRCompositorStatusNoFrameAvailable,"V1 applies bounded nonfatal backpressure");
    readyV1.signaledValue=1;WVRAcquiredStereoFrameV1 old{};old.structSize=sizeof(old);
    require(wvr_compositor_acquire_latest_stereo_frame_v1(&old)==0 && old.producerFrameID==1,"V1 delayed producer eventually acquires");
    wvr_compositor_release_acquired_frame_v1(old.lease);wvr_compositor_pause_v1();
    wvr_compositor_release_object_v1(opaque);
    std::puts("COMPOSITOR BACKPRESSURE CHECKS PASSED");
}}
