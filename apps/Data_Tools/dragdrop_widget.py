"""
Drag and Drop Widget for File Upload
Provides a reusable component with both click-to-upload and drag-drop functionality
"""

import uuid

import ipywidgets as widgets
from IPython.display import HTML, Javascript, display


class DragDropUploadWidget:
    """
    Creates a drag-and-drop file upload widget that integrates with ipywidgets
    Supports both drag-drop and click-to-upload
    """

    def __init__(self, accept="*", multiple=True, description=""):
        """
        Initialize the drag-drop widget

        Args:
            accept: File type filter (e.g., '.csv', '.zip', '*')
            multiple: Allow multiple files
            description: Description text for the widget
        """
        self.accept = accept
        self.multiple = multiple
        self.description = description or "Upload Files"
        self.widget_id = str(uuid.uuid4())[:8]
        self.uploaded_files = {}
        self.file_upload = widgets.FileUpload(
            accept=accept,
            multiple=multiple,
            description="Select Files",
            button_style="info",
            layout=widgets.Layout(width="200px"),
        )

        # Observe file uploads
        self.file_upload.observe(self._handle_file_upload, names="value")

    def _iter_files(self, file_value):
        """Normalize ipywidgets FileUpload value to (name, content) tuples"""
        if not file_value:
            return []
        if isinstance(file_value, dict):
            return [
                (name, self._to_bytes(info.get("content")))
                for name, info in file_value.items()
                if isinstance(info, dict)
            ]
        return [
            (info.get("name"), self._to_bytes(info.get("content")))
            for info in file_value
            if isinstance(info, dict) and info.get("name")
        ]

    @staticmethod
    def _to_bytes(content):
        """Ensure uploaded file content is bytes for downstream processing"""
        if isinstance(content, memoryview):
            return content.tobytes()
        return content

    def _handle_file_upload(self, change):
        """Handle files selected via button click"""
        files = change.get("new") if change else self.file_upload.value
        for filename, content in self._iter_files(files):
            self.uploaded_files[filename] = content

    def get_widget(self):
        """
        Returns the complete drag-drop upload widget

        Returns:
            VBox containing drag-drop area and file list
        """

        # Drag-drop HTML area with Voilà-compatible JavaScript
        dragdrop_html = widgets.HTML(
            value=f"""
            <div id="dragdrop_{self.widget_id}" 
                 style="border: 2px dashed #2196F3; border-radius: 8px; 
                        padding: 30px; text-align: center; background: #f5f5f5;
                        cursor: pointer; transition: all 0.3s ease;
                        min-height: 120px; display: flex; flex-direction: column;
                        justify-content: center; align-items: center; user-select: none;">
                <div style="font-size: 40px; margin-bottom: 10px;">📁</div>
                <div style="font-weight: bold; color: #333; font-size: 16px; margin-bottom: 5px;">
                    Drag files here to upload
                </div>
                <div style="color: #999; font-size: 13px;">
                    or use the select button below
                </div>
            </div>
            
            <script>
            (function() {{
                const dropZone = document.getElementById('dragdrop_{self.widget_id}');
                if (!dropZone) return;
                
                // Prevent default behaviors
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {{
                    dropZone.addEventListener(eventName, preventDefaults, false);
                }});
                
                function preventDefaults(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                }}
                
                // Highlight when dragging over
                ['dragenter', 'dragover'].forEach(eventName => {{
                    dropZone.addEventListener(eventName, highlight, false);
                }});
                
                ['dragleave', 'drop'].forEach(eventName => {{
                    dropZone.addEventListener(eventName, unhighlight, false);
                }});
                
                function highlight(e) {{
                    dropZone.style.borderColor = '#4CAF50';
                    dropZone.style.background = '#e8f5e9';
                }}
                
                function unhighlight(e) {{
                    dropZone.style.borderColor = '#2196F3';
                    dropZone.style.background = '#f5f5f5';
                }}
                
                // Handle drop - trigger the file input's change event
                dropZone.addEventListener('drop', handleDrop, false);
                
                function handleDrop(e) {{
                    const dt = e.dataTransfer;
                    const files = dt.files;
                    
                    if (files && files.length > 0) {{
                        // Find the file input element
                        const fileInput = document.querySelector('input[type="file"]');
                        if (fileInput) {{
                            // Set files using DataTransfer API
                            try {{
                                const dataTransfer = new DataTransfer();
                                for (let i = 0; i < files.length; i++) {{
                                    dataTransfer.items.add(files[i]);
                                }}
                                fileInput.files = dataTransfer.files;
                                fileInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }} catch(err) {{
                                console.log('Drag-drop upload in progress, files will be available via ipywidgets');
                            }}
                        }}
                    }}
                }}
            }})();
            </script>
            """
        )

        # File list display
        file_list_html = widgets.HTML(value=self._get_file_list_html())

        # Update file list when files are uploaded
        def update_list(change):
            file_list_html.value = self._get_file_list_html()

        self.file_upload.observe(update_list, names="value")

        # Container - show description, drag-drop area, file upload button, and file list
        container = widgets.VBox(
            [
                widgets.HTML(value=f"<b>{self.description}</b>"),
                dragdrop_html,
                self.file_upload,
                file_list_html,
            ],
            layout=widgets.Layout(width="100%"),
        )

        return container

    def _get_file_list_html(self):
        """Generate HTML for uploaded files list"""
        files = self._iter_files(self.file_upload.value)
        if not files:
            return "<div style='color: #999; font-size: 13px; margin-top: 10px;'>No files uploaded</div>"

        files_html = (
            "<div style='margin-top: 15px;'><b>Uploaded files:</b><ul style='margin: 8px 0;'>"
        )
        for filename, _ in files:
            files_html += (
                f"<li style='color: #2196F3; font-size: 13px; margin: 5px 0;'>✓ {filename}</li>"
            )
        files_html += "</ul></div>"

        return files_html

    def get_file_upload_widget(self):
        """Get the underlying FileUpload widget for data access"""
        return self.file_upload

    def clear(self):
        """Clear all uploaded files"""
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.uploaded_files.clear()


class DragDropMultiUploadWidget:
    """
    Manages multiple drag-drop upload areas (e.g., for T and R files in UV-Vis merger)
    """

    def __init__(self, sections):
        """
        Initialize with multiple upload sections

        Args:
            sections: List of dicts with keys: 'name', 'accept', 'description'
                     Example: [
                         {'name': 'transmission', 'accept': '.csv', 'description': 'Transmission-Dateien'},
                         {'name': 'reflection', 'accept': '.csv', 'description': 'Reflexions-Dateien'}
                     ]
        """
        self.sections = sections
        self.widgets = {}

        for section in sections:
            self.widgets[section["name"]] = DragDropUploadWidget(
                accept=section.get("accept", "*"),
                multiple=True,
                description=section.get("description", ""),
            )

    def get_widget(self):
        """Returns VBox with all upload sections"""
        children = [widget.get_widget() for widget in self.widgets.values()]
        return widgets.VBox(children, layout=widgets.Layout(width="100%"))

    def get_file_upload_widget(self, section_name):
        """Get FileUpload widget for specific section"""
        return self.widgets[section_name].get_file_upload_widget()

    def clear(self, section_name=None):
        """Clear files from section or all sections"""
        if section_name:
            if section_name in self.widgets:
                self.widgets[section_name].clear()
        else:
            for widget in self.widgets.values():
                widget.clear()


if __name__ == "__main__":
    print("✅ Drag-Drop Widget module loaded")
    print("Available classes: DragDropUploadWidget, DragDropMultiUploadWidget")
