"""
Cross-platform path utilities for LocoDex Deep Research Service
Handles Windows, macOS, and Linux path operations consistently
"""

import os
import platform
from pathlib import Path
from typing import Union


class PlatformPaths:
    """Cross-platform path management for different operating systems"""
    
    @staticmethod
    def get_platform() -> str:
        """Get current platform name"""
        return platform.system().lower()
    
    @staticmethod
    def is_windows() -> bool:
        """Check if running on Windows"""
        return platform.system().lower() == 'windows'
    
    @staticmethod
    def is_docker() -> bool:
        """Check if running inside Docker container"""
        return os.path.exists('/.dockerenv') or os.path.exists('/proc/1/cgroup')
    
    @staticmethod
    def get_base_data_dir() -> Path:
        """Get platform-specific base data directory"""
        if PlatformPaths.is_docker():
            # Docker container paths
            return Path('/app')
        
        system = PlatformPaths.get_platform()
        if system == 'windows':
            # Windows: Use APPDATA or LOCALAPPDATA
            appdata = os.getenv('APPDATA') or os.getenv('LOCALAPPDATA')
            if appdata:
                return Path(appdata) / 'LocoDex'
            return Path.home() / 'AppData' / 'Roaming' / 'LocoDex'
        elif system == 'darwin':
            # macOS: Use Application Support
            return Path.home() / 'Library' / 'Application Support' / 'LocoDex'
        else:
            # Linux and others: Use XDG or home directory
            xdg_data_home = os.getenv('XDG_DATA_HOME')
            if xdg_data_home:
                return Path(xdg_data_home) / 'locodex'
            return Path.home() / '.local' / 'share' / 'locodex'
    
    @staticmethod
    def get_research_results_dir() -> Path:
        """Get research results directory"""
        base_dir = PlatformPaths.get_base_data_dir()
        results_dir = base_dir / 'research_results'
        results_dir.mkdir(parents=True, exist_ok=True)
        return results_dir
    
    @staticmethod
    def get_desktop_dir() -> Path:
        """Get desktop directory - cross-platform"""
        if PlatformPaths.is_docker():
            # Docker container - mounted desktop
            desktop_path = Path('/app/desktop')
            if desktop_path.exists():
                return desktop_path
            # Fallback to container desktop
            return Path('/app/desktop')
        
        system = PlatformPaths.get_platform()
        if system == 'windows':
            # Windows Desktop
            desktop = os.getenv('USERPROFILE')
            if desktop:
                return Path(desktop) / 'Desktop'
            return Path.home() / 'Desktop'
        else:
            # Unix-like systems
            return Path.home() / 'Desktop'
    
    @staticmethod
    def get_temp_dir() -> Path:
        """Get temporary directory"""
        if PlatformPaths.is_docker():
            temp_dir = Path('/tmp/locodex')
        else:
            system = PlatformPaths.get_platform()
            if system == 'windows':
                temp_base = os.getenv('TEMP') or os.getenv('TMP')
                if temp_base:
                    temp_dir = Path(temp_base) / 'LocoDex'
                else:
                    temp_dir = Path.home() / 'AppData' / 'Local' / 'Temp' / 'LocoDex'
            else:
                temp_dir = Path('/tmp/locodex')
        
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    @staticmethod
    def get_logs_dir() -> Path:
        """Get logs directory"""
        base_dir = PlatformPaths.get_base_data_dir()
        logs_dir = base_dir / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir
    
    @staticmethod  
    def get_cache_dir() -> Path:
        """Get cache directory"""
        if PlatformPaths.is_docker():
            cache_dir = Path('/app/cache')
        else:
            system = PlatformPaths.get_platform()
            if system == 'windows':
                localappdata = os.getenv('LOCALAPPDATA')
                if localappdata:
                    cache_dir = Path(localappdata) / 'LocoDex' / 'cache'
                else:
                    cache_dir = Path.home() / 'AppData' / 'Local' / 'LocoDex' / 'cache'
            elif system == 'darwin':
                cache_dir = Path.home() / 'Library' / 'Caches' / 'LocoDex'
            else:
                xdg_cache_home = os.getenv('XDG_CACHE_HOME')
                if xdg_cache_home:
                    cache_dir = Path(xdg_cache_home) / 'locodex'
                else:
                    cache_dir = Path.home() / '.cache' / 'locodex'
        
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    @staticmethod
    def normalize_path(path: Union[str, Path]) -> Path:
        """Normalize path for current platform"""
        path_obj = Path(path)
        
        # Resolve to absolute path
        if not path_obj.is_absolute():
            path_obj = Path.cwd() / path_obj
        
        return path_obj.resolve()
    
    @staticmethod
    def create_safe_filename(text: str, max_length: int = 50) -> str:
        """Create a safe filename from text"""
        # Remove invalid characters for Windows and Unix
        invalid_chars = '<>:"/\\|?*'
        safe_text = ''.join(c for c in text if c not in invalid_chars)
        
        # Replace spaces with underscores
        safe_text = safe_text.replace(' ', '_')
        
        # Remove control characters
        safe_text = ''.join(c for c in safe_text if ord(c) >= 32)
        
        # Limit length
        if len(safe_text) > max_length:
            safe_text = safe_text[:max_length]
        
        # Ensure it doesn't end with a period (Windows issue)
        safe_text = safe_text.rstrip('.')
        
        # Ensure it's not empty
        if not safe_text:
            safe_text = 'untitled'
        
        return safe_text
    
    @staticmethod
    def get_research_file_path(topic: str, timestamp: str = None) -> Path:
        """Get full path for research result file"""
        from datetime import datetime
        
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        safe_topic = PlatformPaths.create_safe_filename(topic)
        filename = f"{timestamp}_{safe_topic}.md"
        
        return PlatformPaths.get_research_results_dir() / filename
    
    @staticmethod
    def get_available_space(path: Union[str, Path]) -> int:
        """Get available disk space in bytes"""
        import shutil
        
        try:
            return shutil.disk_usage(str(path)).free
        except (OSError, AttributeError):
            # Fallback for older Python versions or permission issues
            return -1


# Convenience functions for backward compatibility
def get_research_results_dir() -> Path:
    """Get research results directory - legacy function"""
    return PlatformPaths.get_research_results_dir()


def get_desktop_dir() -> Path:
    """Get desktop directory - legacy function"""
    return PlatformPaths.get_desktop_dir()


def create_safe_filename(text: str) -> str:
    """Create safe filename - legacy function"""
    return PlatformPaths.create_safe_filename(text)


# Debug information
if __name__ == "__main__":
    print("LocoDex Path Utils - Platform Information")
    print(f"Platform: {PlatformPaths.get_platform()}")
    print(f"Is Windows: {PlatformPaths.is_windows()}")
    print(f"Is Docker: {PlatformPaths.is_docker()}")
    print(f"Base Data Dir: {PlatformPaths.get_base_data_dir()}")
    print(f"Research Results: {PlatformPaths.get_research_results_dir()}")
    print(f"Desktop Dir: {PlatformPaths.get_desktop_dir()}")
    print(f"Temp Dir: {PlatformPaths.get_temp_dir()}")
    print(f"Logs Dir: {PlatformPaths.get_logs_dir()}")
    print(f"Cache Dir: {PlatformPaths.get_cache_dir()}")