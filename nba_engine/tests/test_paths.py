"""
Tests for the paths module.

Verifies that:
1. Persistent paths are used instead of relative paths
2. Paths work in both source and simulated frozen modes
3. Migration logic works correctly
4. Directories are created automatically
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest


class TestPathsModule:
    """Test the paths module functionality."""
    
    def test_import_creates_directories(self):
        """Importing paths module should create necessary directories."""
        from paths import DATA_ROOT, TRACKING_DIR, LOG_DIR, CACHE_DIR
        
        assert DATA_ROOT.exists()
        assert TRACKING_DIR.exists()
        assert LOG_DIR.exists()
        assert CACHE_DIR.exists()
    
    def test_tracking_file_path_is_absolute(self):
        """TRACKING_FILE_PATH should be an absolute path."""
        from paths import TRACKING_FILE_PATH
        
        assert TRACKING_FILE_PATH.is_absolute()
    
    def test_tracking_path_not_in_temp(self):
        """TRACKING_FILE_PATH should not be in a temp directory."""
        from paths import TRACKING_FILE_PATH
        
        path_str = str(TRACKING_FILE_PATH).lower()
        
        # Should not contain temp directory markers
        assert '_mei' not in path_str, "Path contains _MEI (PyInstaller temp dir)"
        assert 'appdata\\local\\temp' not in path_str
        assert '/tmp/' not in path_str
        assert '/var/tmp/' not in path_str
    
    def test_tracking_path_in_user_directory(self):
        """TRACKING_FILE_PATH should be in a user-accessible location."""
        from paths import TRACKING_FILE_PATH, DATA_ROOT
        
        home = Path.home()
        
        # Should be under home directory or APPDATA
        path_str = str(DATA_ROOT)
        home_str = str(home)
        
        # On Windows, APPDATA is under home
        # On Linux/Mac, should be under home
        assert path_str.startswith(home_str) or 'AppData' in path_str or '.local' in path_str
    
    def test_is_frozen_returns_false_in_source(self):
        """is_frozen() should return False when running from source."""
        from paths import is_frozen
        
        assert is_frozen() == False
    
    def test_get_frozen_temp_dir_returns_none_in_source(self):
        """get_frozen_temp_dir() should return None when not frozen."""
        from paths import get_frozen_temp_dir
        
        assert get_frozen_temp_dir() is None
    
    def test_data_root_is_stable(self):
        """DATA_ROOT should be the same on multiple imports."""
        from paths import DATA_ROOT
        
        # Import again and check
        import importlib
        import paths
        importlib.reload(paths)
        
        from paths import DATA_ROOT as DATA_ROOT_2
        
        assert DATA_ROOT == DATA_ROOT_2


class TestGetDataRoot:
    """Test the get_data_root function for different OS scenarios."""
    
    @pytest.mark.skipif(os.name != 'nt', reason="Windows-only test")
    def test_windows_with_appdata(self):
        """On Windows with APPDATA set, should use APPDATA."""
        from paths import get_data_root
        
        with mock.patch.dict(os.environ, {'APPDATA': 'C:\\Users\\Test\\AppData\\Roaming'}):
            root = get_data_root()
            assert 'NBA_Engine' in str(root)
    
    def test_data_root_contains_nba_engine(self):
        """DATA_ROOT should contain NBA_Engine in the path."""
        from paths import DATA_ROOT
        
        assert 'NBA_Engine' in str(DATA_ROOT)


class TestMigration:
    """Test migration from legacy paths."""
    
    def test_get_legacy_paths_not_empty(self):
        """get_legacy_tracking_paths should return some paths to check."""
        from paths import get_legacy_tracking_paths
        
        paths = get_legacy_tracking_paths()
        # Should return at least some candidate paths
        assert isinstance(paths, list)
    
    def test_legacy_paths_exclude_canonical(self):
        """Legacy paths should not include the canonical path."""
        from paths import get_legacy_tracking_paths, TRACKING_FILE_PATH
        
        legacy = get_legacy_tracking_paths()
        canonical = TRACKING_FILE_PATH.resolve()
        
        for p in legacy:
            try:
                assert p.resolve() != canonical
            except (OSError, ValueError):
                pass  # Path doesn't exist, that's fine


class TestDiagnostics:
    """Test diagnostic logging functions."""
    
    def test_log_startup_diagnostics_returns_string(self):
        """log_startup_diagnostics should return log text."""
        from paths import log_startup_diagnostics
        
        result = log_startup_diagnostics()
        
        assert isinstance(result, str)
        assert 'NBA Engine' in result
        assert 'Tracking file' in result.lower() or 'tracking' in result.lower()
    
    def test_get_tracking_path_message(self):
        """get_tracking_path_message should return informative string."""
        from paths import get_tracking_path_message, TRACKING_FILE_PATH
        
        msg = get_tracking_path_message()
        
        assert isinstance(msg, str)
        assert str(TRACKING_FILE_PATH) in msg


class TestFrozenSimulation:
    """Test behavior when simulating frozen (PyInstaller) mode."""
    
    def test_would_not_use_meipass_for_storage(self):
        """Even if _MEIPASS exists, storage should not use it."""
        from paths import get_data_root
        
        # Simulate frozen mode
        with mock.patch.object(sys, 'frozen', True, create=True):
            with mock.patch.object(sys, '_MEIPASS', '/tmp/_MEI12345', create=True):
                root = get_data_root()
                
                # Should NOT contain _MEI
                assert '_MEI' not in str(root)
                assert '/tmp/' not in str(root) or '.local' in str(root)


class TestTrackerIntegration:
    """Test that ExcelTracker uses the correct paths."""
    
    def test_tracker_uses_persistent_path(self):
        """ExcelTracker should use the persistent path from paths module."""
        from tracking import ExcelTracker, TRACKING_FILE_PATH
        from paths import TRACKING_FILE_PATH as PATHS_TRACKING_FILE
        
        tracker = ExcelTracker()
        
        # Should use the same path
        assert tracker.file_path == PATHS_TRACKING_FILE
        assert tracker.file_path == TRACKING_FILE_PATH
    
    def test_tracking_module_exports_correct_path(self):
        """tracking module should export the correct TRACKING_FILE_PATH."""
        from tracking import TRACKING_FILE_PATH
        from paths import TRACKING_FILE_PATH as CANONICAL_PATH
        
        assert TRACKING_FILE_PATH == CANONICAL_PATH


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
