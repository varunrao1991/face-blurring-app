import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFileDialog, QScrollArea,
                             QMessageBox, QLineEdit, QGridLayout, QSlider)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PyQt5.QtCore import Qt, QDir, QSize
from PyQt5 import QtCore
from PIL import Image

class FaceBlurerApp(QWidget):
    def __init__(self, default_root_folder=None):
        super().__init__()
        self.root_folder = default_root_folder if default_root_folder else ""
        self.image_files = []
        self.current_image_index = 0
        self.face_data = {}  # {filepath: {faces: [(x, y, w, h)], selected: [True, False, ...], blurred: image}}
        self.face_preview_size = 100  # Size of face preview thumbnails
        self.blur_amount_percent = 50  # Default blur amount (must be odd)
        self.initUI()
        if self.root_folder:
            self.root_path_field.setText(self.root_folder)
            self._load_initial_images()

    def initUI(self):
        self.setWindowTitle("Recursive Face Blurer")
        self.setGeometry(100, 100, 1200, 700)  # Increased width for side panel

        # Root Folder Selection
        self.root_label = QLabel("Root Folder:")
        self.root_path_field = QLineEdit()
        self.root_path_field.setReadOnly(True)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_folder)

        root_layout = QHBoxLayout()
        root_layout.addWidget(self.root_label)
        root_layout.addWidget(self.root_path_field)
        root_layout.addWidget(self.browse_button)

        # Blur amount slider
        self.blur_slider_label = QLabel("Blur Amount:")
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setMinimum(0)
        self.blur_slider.setMaximum(100)
        self.blur_slider.setSingleStep(1)
        self.blur_slider.setValue(self.blur_amount_percent)
        self.blur_slider.valueChanged.connect(self.update_blur_amount)
        self.blur_value_label = QLabel(f"{self.blur_amount_percent}")

        blur_layout = QHBoxLayout()
        blur_layout.addWidget(self.blur_slider_label)
        blur_layout.addWidget(self.blur_slider)
        blur_layout.addWidget(self.blur_value_label)

        # Main content area
        content_layout = QHBoxLayout()

        # Left side - main image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.image_label)

        # Right side - face preview grid
        self.face_preview_container = QWidget()
        self.face_preview_layout = QGridLayout()
        self.face_preview_title = QLabel("Select Faces to Blur (Green = Blurred)")
        self.face_preview_container.setLayout(QVBoxLayout())
        self.face_preview_container.layout().addWidget(self.face_preview_title)
        
        # Add a scroll area for the face previews
        self.face_preview_scroll = QScrollArea()
        self.face_preview_widget = QWidget()
        self.face_preview_widget.setLayout(self.face_preview_layout)
        self.face_preview_scroll.setWidget(self.face_preview_widget)
        self.face_preview_scroll.setWidgetResizable(True)
        self.face_preview_container.layout().addWidget(self.face_preview_scroll)
        
        content_layout.addWidget(self.scroll_area, 70)  # 70% width
        content_layout.addWidget(self.face_preview_container, 30)  # 30% width

        # Buttons
        self.next_button = QPushButton("Next Image")
        self.next_button.clicked.connect(self.load_next_image)
        self.next_button.setEnabled(False)

        self.prev_button = QPushButton("Previous Image")
        self.prev_button.clicked.connect(self.load_previous_image)
        self.prev_button.setEnabled(False)

        self.save_all_button = QPushButton("Save All Images")
        self.save_all_button.clicked.connect(self.save_all_images)
        self.save_all_button.setEnabled(False)

        self.redetect_button = QPushButton("Redetect Faces")
        self.redetect_button.clicked.connect(self._redetect_faces)
        self.redetect_button.setEnabled(False)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.prev_button)
        controls_layout.addWidget(self.next_button)
        controls_layout.addWidget(self.save_all_button)
        controls_layout.addWidget(self.redetect_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(root_layout)
        main_layout.addLayout(blur_layout)
        main_layout.addLayout(content_layout)
        main_layout.addLayout(controls_layout)

        self.setLayout(main_layout)
        self.show()

    def update_blur_amount(self, value):
        # Ensure blur amount is odd (required by GaussianBlur)
        self.blur_amount_percent = value
        self.blur_slider.setValue(self.blur_amount_percent)
        self.blur_value_label.setText(f"{self.blur_amount_percent}%")
        
        # Re-apply blur to all images with the new amount
        for filepath in self.face_data:
            if self.face_data[filepath]['selected']:
                self.apply_blur_instant(filepath)

    def _load_initial_images(self):
        self.image_files = self.load_image_files(self.root_folder)
        self.current_image_index = 0
        if self.image_files:
            self.load_current_image()
            self.next_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.save_all_button.setEnabled(True)
            self.redetect_button.setEnabled(True)
        else:
            self.image_label.clear()
            QMessageBox.information(self, "Info", "No image files found in the specified folder.")
            self.next_button.setEnabled(False)
            self.prev_button.setEnabled(False)
            self.save_all_button.setEnabled(False)
            self.redetect_button.setEnabled(False)

    def browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Root Folder")
        if folder_path:
            self.root_folder = folder_path
            self.root_path_field.setText(folder_path)
            self._load_initial_images()

    def load_image_files(self, folder):
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        files = []
        for item in QDir(folder).entryInfoList(QDir.Files | QDir.Dirs | QDir.NoDotAndDotDot | QDir.Hidden):
            file_path = item.filePath()
            if item.isDir():
                files.extend(self.load_image_files(file_path))
            elif item.isFile():
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension in image_extensions:
                    files.append(file_path)
        return files

    def load_image_cv(self, filepath):
        try:
            image = cv2.imread(filepath)
            if image is None:
                if filepath.lower().endswith('.webp'):
                    img_pil = Image.open(filepath).convert("RGB")
                    image = np.array(img_pil)
                    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                else:
                    return None
            return image
        except Exception as e:
            print(f"Error loading image with OpenCV: {filepath} - {e}")
            return None

    def load_current_image(self):
        if not self.image_files:
            self.image_label.clear()
            QMessageBox.information(self, "Info", "No image files loaded.")
            return

        filepath = self.image_files[self.current_image_index]
        self.setWindowTitle(f"Recursive Face Blurer - {os.path.basename(filepath)}")
        image = self.load_image_cv(filepath)
        if image is None:
            QMessageBox.warning(self, "Warning", f"Could not open or find the image: {filepath}")
            self.image_label.clear()
            return

        # Only detect faces if we haven't already
        if filepath not in self.face_data:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(20, 20))
            self.face_data[filepath] = {'faces': faces, 'selected': [True] * len(faces), 'blurred': None}
        
        # Apply blur based on current selections
        self.apply_blur_instant(filepath)
        self.update_face_previews(filepath)

    def _redetect_faces(self):
        if not self.image_files:
            return
        filepath = self.image_files[self.current_image_index]
        image = self.load_image_cv(filepath)
        if image is None:
            return
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        # Keep existing selections if possible
        old_data = self.face_data.get(filepath, {'selected': []})
        new_selected = [True] * len(faces)
        
        # Try to match old selections with new faces (very basic matching)
        if len(old_data['selected']) == len(faces):
            new_selected = old_data['selected']
        
        self.face_data[filepath] = {'faces': faces, 'selected': new_selected, 'blurred': None}
        self.apply_blur_instant(filepath)
        self.update_face_previews(filepath)

    def display_image(self, image, filepath):
        h, w, ch = image.shape
        bytes_per_line = ch * w
        q_image = QImage(image.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pixmap = QPixmap.fromImage(q_image)

        if filepath in self.face_data:
            painter = QPainter(pixmap)
            faces = self.face_data[filepath]['faces']
            selected = self.face_data[filepath]['selected']
            
            for i, (x, y, width, height) in enumerate(faces):
                # Use green for selected faces (will be blurred), red for unselected
                color = QColor(0, 255, 0) if selected[i] else QColor(255, 0, 0)
                pen = QPen(color, 2)
                painter.setPen(pen)
                painter.drawRect(x, y, width, height)
            painter.end()

        scaled_pixmap = pixmap.scaled(self.scroll_area.width() - 20, self.scroll_area.height() - 20,
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)

    def apply_blur_instant(self, filepath):
        if filepath not in self.face_data:
            return

        original_image = self.load_image_cv(filepath)
        if original_image is None:
            return

        faces = self.face_data[filepath]['faces']
        selected = self.face_data[filepath]['selected']
        blurred_image = original_image.copy()

        for i, (x, y, w, h) in enumerate(faces):
            if selected[i]:
                roi = blurred_image[y:y+h, x:x+w]
                # Calculate blur size based on percentage of face width (0-1)
                blur_factor = self.blur_amount_percent / 100.0
                blur_size = int(w * blur_factor)
                # Ensure blur_amount is odd and at least 1
                blur_amount = max(1, blur_size // 2 * 2 + 1)
                blur = cv2.GaussianBlur(roi, (blur_amount, blur_amount), 30)
                blurred_image[y:y+h, x:x+w] = blur

        self.face_data[filepath]['blurred'] = blurred_image
        self.display_image(blurred_image, filepath)

    def update_face_previews(self, filepath):
        # Clear existing previews
        for i in reversed(range(self.face_preview_layout.count())): 
            self.face_preview_layout.itemAt(i).widget().setParent(None)
            
        if filepath not in self.face_data:
            return
            
        image = self.load_image_cv(filepath)
        if image is None:
            return
            
        faces = self.face_data[filepath]['faces']
        selected = self.face_data[filepath]['selected']
        
        for i, (x, y, w, h) in enumerate(faces):
            # Extract face region
            face_img = image[y:y+h, x:x+w].copy()
            
            # Create preview label
            preview_label = QLabel()
            preview_label.setFixedSize(QSize(self.face_preview_size, self.face_preview_size))
            preview_label.mousePressEvent = lambda event, idx=i: self.toggle_face_selection(filepath, idx)
            
            # Convert to QPixmap
            h, w, ch = face_img.shape
            bytes_per_line = ch * w
            q_img = QImage(face_img.data, w, h, bytes_per_line, QImage.Format_BGR888)
            pixmap = QPixmap.fromImage(q_img)
            
            # Scale and add border color based on selection
            scaled_pix = pixmap.scaled(
                self.face_preview_size - 4, self.face_preview_size - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            
            # Create bordered pixmap
            bordered_pix = QPixmap(self.face_preview_size, self.face_preview_size)
            bordered_pix.fill(Qt.transparent)
            
            painter = QPainter(bordered_pix)
            border_color = QColor(0, 255, 0) if selected[i] else QColor(255, 0, 0)
            painter.setPen(QPen(border_color, 2))
            painter.drawRect(0, 0, self.face_preview_size - 1, self.face_preview_size - 1)
            
            # Center the face in the preview
            x_pos = (self.face_preview_size - scaled_pix.width()) // 2
            y_pos = (self.face_preview_size - scaled_pix.height()) // 2
            painter.drawPixmap(x_pos, y_pos, scaled_pix)
            painter.end()
            
            preview_label.setPixmap(bordered_pix)
            self.face_preview_layout.addWidget(preview_label, i // 3, i % 3)

    def toggle_face_selection(self, filepath, face_index):
        if filepath in self.face_data and 0 <= face_index < len(self.face_data[filepath]['selected']):
            self.face_data[filepath]['selected'][face_index] = not self.face_data[filepath]['selected'][face_index]
            self.apply_blur_instant(filepath)
            self.update_face_previews(filepath)

    def load_next_image(self):
        if self.image_files:
            self.current_image_index = (self.current_image_index + 1) % len(self.image_files)
            self.load_current_image()

    def load_previous_image(self):
        if self.image_files:
            self.current_image_index = (self.current_image_index - 1 + len(self.image_files)) % len(self.image_files)
            self.load_current_image()

    def save_all_images(self):
        if not self.image_files:
            return
            
        reply = QMessageBox.question(self, 'Confirm Save', 
                                   'This will overwrite all original images. Continue?',
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.No:
            return
            
        progress = 0
        progress_dialog = QMessageBox(self)
        progress_dialog.setWindowTitle("Saving Images")
        progress_dialog.setText(f"Saving images... {progress}/{len(self.image_files)}")
        progress_dialog.setStandardButtons(QMessageBox.Cancel)
        progress_dialog.show()
        
        for i, filepath in enumerate(self.image_files):
            if filepath in self.face_data and self.face_data[filepath]['blurred'] is not None:
                try:
                    # Determine the original format
                    extension = os.path.splitext(filepath)[1].lower()
                    if extension == '.webp':
                        img_pil = Image.fromarray(cv2.cvtColor(self.face_data[filepath]['blurred'], cv2.COLOR_BGR2RGB))
                        img_pil.save(filepath, "webp")
                    else:
                        cv2.imwrite(filepath, self.face_data[filepath]['blurred'])
                except Exception as e:
                    print(f"Error saving image {filepath}: {e}")
            
            progress = i + 1
            progress_dialog.setText(f"Saving images... {progress}/{len(self.image_files)}")
            QApplication.processEvents()  # Keep the UI responsive
            
            if progress_dialog.clickedButton():
                break
        
        progress_dialog.close()
        QMessageBox.information(self, "Info", f"Saved {progress} images.")

if __name__ == '__main__':
    default_root = None
    if len(sys.argv) > 1:
        default_root = sys.argv[1]
    app = QApplication(sys.argv)
    ex = FaceBlurerApp(default_root)
    sys.exit(app.exec_())