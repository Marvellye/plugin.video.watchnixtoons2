# -*- coding: utf-8 -*-
import os
import xbmc
import xbmcgui
from lib.network import rqs_get
from lib.constants import WNT2_USER_AGENT, BASEURL

class DownloadManager:
    def __init__(self):
        self._dialog = xbmcgui.DialogProgressBG()

    def download(self, url, dest_folder, filename_prefix, headers=None):
        if not headers:
            headers = {
                'User-Agent': WNT2_USER_AGENT,
                'Referer': BASEURL + '/',
            }

        # Initial notification or state
        self._dialog.create('Starting Download', filename_prefix)
        
        try:
            response = rqs_get().get(url, stream=True, headers=headers, verify=False, timeout=30)
            
            if not response.ok:
                self._dialog.close()
                xbmcgui.Dialog().notification('Download Failed', 'HTTP ' + str(response.status_code), xbmcgui.NOTIFICATION_ERROR)
                return

            # Determine file extension
            content_type = response.headers.get('Content-Type', 'video/mp4').lower()
            if 'mp4' in content_type:
                file_ext = '.mp4'
            elif 'webm' in content_type:
                file_ext = '.webm'
            elif 'ogg' in content_type or 'ogv' in content_type:
                file_ext = '.ogv'
            elif 'quicktime' in content_type:
                file_ext = '.mov'
            else:
                file_ext = '.mp4'

            filename = filename_prefix + file_ext
            filepath = os.path.join(dest_folder, filename)

            # Update dialog with real filename
            self._dialog.update(0, heading='Downloading: ' + filename, message='0%')

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self._dialog.update(percent, heading='Downloading: ' + filename, message=str(percent) + '%')
            
            self._dialog.close()
            xbmcgui.Dialog().notification('Download Completed', filename, xbmcgui.NOTIFICATION_INFO)

        except Exception as e:
            self._dialog.close()
            xbmcgui.Dialog().notification('Download Error', str(e), xbmcgui.NOTIFICATION_ERROR)