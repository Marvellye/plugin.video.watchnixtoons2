# -*- coding: utf-8 -*-
import os
import json
import time
import uuid
import xbmc
import xbmcgui
from lib.network import rqs_get
from lib.constants import WNT2_USER_AGENT, BASEURL

PROP_DOWNLOADS = 'wnt2_downloads_list'

class DownloadManager:
    def __init__(self):
        self.window = xbmcgui.Window(10000)

    def _get_all_ids(self):
        data = self.window.getProperty(PROP_DOWNLOADS)
        try:
            return json.loads(data) if data else []
        except:
            return []

    def _save_all_ids(self, ids):
        self.window.setProperty(PROP_DOWNLOADS, json.dumps(ids))

    def _get_task(self, task_id):
        data = self.window.getProperty(PROP_DOWNLOADS + '.' + task_id)
        try:
            return json.loads(data) if data else None
        except:
            return None

    def _save_task(self, task_id, data):
        self.window.setProperty(PROP_DOWNLOADS + '.' + task_id, json.dumps(data))

    def _remove_task(self, task_id):
        self.window.clearProperty(PROP_DOWNLOADS + '.' + task_id)

    def get_tasks(self):
        ids = self._get_all_ids()
        tasks = []
        clean_ids = []
        for i in ids:
            t = self._get_task(i)
            if t:
                tasks.append(t)
                clean_ids.append(i)
        
        if len(clean_ids) != len(ids):
            self._save_all_ids(clean_ids)
            
        return tasks

    def download(self, url, dest_folder, filename_prefix, headers=None):
        task_id = str(uuid.uuid4())
        
        if not headers:
            headers = {
                'User-Agent': WNT2_USER_AGENT,
                'Referer': BASEURL + '/',
            }

        task_data = {
            'id': task_id,
            'name': filename_prefix,
            'status': 'pending',
            'progress': 0,
            'filepath': '',
            'error': ''
        }
        
        self._save_task(task_id, task_data)
        
        ids = self._get_all_ids()
        ids.append(task_id)
        self._save_all_ids(ids)

        xbmcgui.Dialog().notification('Download Started', filename_prefix, xbmcgui.NOTIFICATION_INFO)
        
        try:
            task_data['status'] = 'downloading'
            self._save_task(task_id, task_data)

            response = rqs_get().get(url, stream=True, headers=headers, verify=False, timeout=30)
            
            if not response.ok:
                raise Exception('HTTP ' + str(response.status_code))

            # Determine file extension
            content_type = response.headers.get('Content-Type', 'video/mp4').lower()
            if 'mp4' in content_type: file_ext = '.mp4'
            elif 'webm' in content_type: file_ext = '.webm'
            elif 'ogg' in content_type or 'ogv' in content_type: file_ext = '.ogv'
            elif 'quicktime' in content_type: file_ext = '.mov'
            else: file_ext = '.mp4'

            filename = filename_prefix + file_ext
            filepath = os.path.join(dest_folder, filename)
            
            task_data['filepath'] = filepath
            self._save_task(task_id, task_data)

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_update = 0
            chunk_count = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    chunk_count += 1
                    if chunk_count % 20 == 0:
                        current_task = self._get_task(task_id)
                        if not current_task or current_task.get('status') == 'cancelling':
                            f.close()
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            if current_task:
                                current_task['status'] = 'cancelled'
                                self._save_task(task_id, current_task)
                            return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            if percent > last_update:
                                task_data['progress'] = percent
                                self._save_task(task_id, task_data)
                                last_update = percent

            task_data['status'] = 'completed'
            task_data['progress'] = 100
            self._save_task(task_id, task_data)
            xbmcgui.Dialog().notification('Download Completed', filename, xbmcgui.NOTIFICATION_INFO)

        except Exception as e:
            task_data['status'] = 'error'
            task_data['error'] = str(e)
            self._save_task(task_id, task_data)
            xbmcgui.Dialog().notification('Download Error', str(e), xbmcgui.NOTIFICATION_ERROR)

    def cancel(self, task_id):
        task = self._get_task(task_id)
        if task and task['status'] in ['pending', 'downloading']:
            task['status'] = 'cancelling'
            self._save_task(task_id, task)

    def remove(self, task_id):
        self.cancel(task_id)
        ids = self._get_all_ids()
        if task_id in ids:
            ids.remove(task_id)
            self._save_all_ids(ids)
        self._remove_task(task_id)