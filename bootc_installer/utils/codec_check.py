import logging

logger = logging.getLogger("Installer::CodecCheck")

HAS_GST = False
try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    HAS_GST = True
except (ImportError, ValueError) as e:
    logger.warning("GStreamer python bindings (gi.repository.Gst) not available: %s", e)
    Gst = None

def check_codecs_present() -> dict[str, bool]:
    """Check if VP9 and AV1 decoders are registered in the GStreamer registry.
    
    Returns a dict with 'vp9' and 'av1' mapping to booleans.
    """
    codecs = {"vp9": False, "av1": False}
    if not HAS_GST or Gst is None:
        return codecs
        
    try:
        if not Gst.is_initialized():
            Gst.init(None)
        
        registry = Gst.Registry.get()
        
        # Look for VP9 decoders
        vp9_decoders = ["vp9dec", "vaapivp9dec", "nvdec_vp9", "v4l2vp9dec"]
        for dec in vp9_decoders:
            if registry.find_feature(dec, Gst.ElementFactory.__gtype__) is not None:
                codecs["vp9"] = True
                logger.info("Found GStreamer VP9 decoder: %s", dec)
                break
                
        # Look for AV1 decoders
        av1_decoders = ["av1dec", "dav1ddec", "vaapiav1dec", "nvdec_av1", "v4l2av1dec"]
        for dec in av1_decoders:
            if registry.find_feature(dec, Gst.ElementFactory.__gtype__) is not None:
                codecs["av1"] = True
                logger.info("Found GStreamer AV1 decoder: %s", dec)
                break
                
    except Exception as e:
        logger.error("Error occurred during GStreamer codec inspection: %s", e)
        
    return codecs
