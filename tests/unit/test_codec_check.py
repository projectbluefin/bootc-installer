import sys
from unittest.mock import MagicMock, patch
import pytest

def test_codec_check_when_gst_missing():
    """Verify that when GStreamer bindings are missing, check returns False for both codecs."""
    with patch("gi.require_version", side_effect=ValueError("Gst unavailable")):
        sys.modules.pop("bootc_installer.utils.codec_check", None)
        import bootc_installer.utils.codec_check as cc
        
        codecs = cc.check_codecs_present()
        assert codecs["vp9"] is False
        assert codecs["av1"] is False

def test_codec_check_when_gst_present_and_codecs_found():
    """Verify that when GStreamer is present and codecs exist, check returns True."""
    gst_mock = MagicMock()
    gst_mock.is_initialized.return_value = False
    
    # Mock ElementFactory GType explicitly since double-underscores are not auto-mocked
    element_factory_mock = MagicMock()
    element_factory_mock.__gtype__ = "element_factory_gtype"
    gst_mock.ElementFactory = element_factory_mock
    
    registry_mock = MagicMock()
    gst_mock.Registry.get.return_value = registry_mock
    
    # Simulate finding specific decoders
    def _find_feature(name, _type):
        if name in ["vp9dec", "av1dec"]:
            return MagicMock()
        return None
        
    registry_mock.find_feature.side_effect = _find_feature
    
    with patch("gi.require_version"):
        sys.modules.pop("bootc_installer.utils.codec_check", None)
        import bootc_installer.utils.codec_check as cc
        
        cc.Gst = gst_mock
        cc.HAS_GST = True
        
        codecs = cc.check_codecs_present()
        assert codecs["vp9"] is True
        assert codecs["av1"] is True
        
        gst_mock.init.assert_called_once()

def test_codec_check_when_gst_present_but_codecs_missing():
    """Verify that when GStreamer is present but no VP9/AV1 codecs are registered, check returns False."""
    gst_mock = MagicMock()
    gst_mock.is_initialized.return_value = True
    
    # Mock ElementFactory GType explicitly since double-underscores are not auto-mocked
    element_factory_mock = MagicMock()
    element_factory_mock.__gtype__ = "element_factory_gtype"
    gst_mock.ElementFactory = element_factory_mock
    
    registry_mock = MagicMock()
    gst_mock.Registry.get.return_value = registry_mock
    registry_mock.find_feature.return_value = None
    
    with patch("gi.require_version"):
        sys.modules.pop("bootc_installer.utils.codec_check", None)
        import bootc_installer.utils.codec_check as cc
        
        cc.Gst = gst_mock
        cc.HAS_GST = True
        
        codecs = cc.check_codecs_present()
        assert codecs["vp9"] is False
        assert codecs["av1"] is False
        
        gst_mock.init.assert_not_called()  # Already initialized
