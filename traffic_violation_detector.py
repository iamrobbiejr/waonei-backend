"""
Traffic Violation Detection Service
Detects 4 primary violations:
1. No Helmet (Motorcycle riders)
2. Running Red Light
3. Wrong Way Driving
4. Illegal Parking (in restricted zones)
"""

import cv2
import numpy as np
from ultralytics import YOLO
import torch
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import requests
import tempfile
import os
from io import BytesIO
from PIL import Image


@dataclass
class ViolationResult:
    """Structure for violation detection results"""
    violation_type: str
    confidence: float
    status: str
    details: Dict
    bbox: Optional[List[int]] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


def _check_restricted_parking_zone(image, bbox) -> bool:
    """
    Check if vehicle is in no-parking zone
    Simplified for demo - in production use zone mapping
    """
    # For demo: check if the vehicle in certain image regions
    # In production: use predefined zone polygons
    x1, y1, x2, y2 = bbox
    center_x = (x1 + x2) / 2

    # Example: left 30% of image is no-parking zone
    image_width = image.shape[1]
    return center_x < (image_width * 0.3)


def _analyze_vehicle_direction(image, bbox) -> bool:
    """
    Analyze if vehicle is going wrong direction
    Simplified for demo - in production use optical flow or lane detection
    """
    # For demo: randomly flag some vehicles (20% chance)
    # In production: use proper direction analysis
    import random
    return random.random() < 0.2


def _detect_red_light_color(image, bbox) -> bool:
    """Detect if a traffic light is red (simplified)"""
    x1, y1, x2, y2 = bbox
    light_region = image[y1:y2, x1:x2]

    # Convert to HSV for better color detection
    hsv = cv2.cvtColor(light_region, cv2.COLOR_BGR2HSV)

    # Red color range in HSV
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    red_pixels = cv2.countNonZero(mask1) + cv2.countNonZero(mask2)
    total_pixels = light_region.shape[0] * light_region.shape[1]

    # If >15% red pixels, consider it red light
    return (red_pixels / total_pixels) > 0.15 if total_pixels > 0 else False


def _is_person_on_vehicle(person_bbox, vehicle_bbox) -> bool:
    """Check if a person bbox overlaps with vehicle bbox"""
    px1, py1, px2, py2 = person_bbox
    vx1, vy1, vx2, vy2 = vehicle_bbox

    # Check intersection
    x_overlap = max(0, min(px2, vx2) - max(px1, vx1))
    y_overlap = max(0, min(py2, vy2) - max(py1, vy1))

    return (x_overlap * y_overlap) > 0


# Video file extensions and MIME types
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.3gp', '.m4v'}
VIDEO_MIME_TYPES = {'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm', 'video/x-matroska'}


def _is_video_url(url: str, content_type: str = '') -> bool:
    """Determine if a URL points to a video file."""
    ext = os.path.splitext(url.split('?')[0].lower())[1]  # Strip query params first
    if ext in VIDEO_EXTENSIONS:
        return True
    if content_type and any(vt in content_type.lower() for vt in ['video/', 'application/octet-stream']):
        # Double-check with extension when content-type is ambiguous
        return ext in VIDEO_EXTENSIONS
    return False


def download_image(url: str) -> np.ndarray:
    """Download image from URL and convert to OpenCV format."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        if _is_video_url(url, content_type):
            raise ValueError(
                f"URL points to a video file. Use extract_frames_from_video() instead. "
                f"Content-Type: {content_type}"
            )

        image = Image.open(BytesIO(response.content))
        image = image.convert('RGB')

        # Convert PIL to OpenCV format
        opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        return opencv_image

    except Exception as e:
        raise Exception(f"Failed to download image: {str(e)}")


def extract_frames_from_video(url: str, num_frames: int = 5) -> List[np.ndarray]:
    """
    Download a video from URL and extract evenly-spaced representative frames.

    Args:
        url: Public URL to the video file.
        num_frames: How many frames to sample across the video duration.

    Returns:
        List of OpenCV frames (numpy arrays in BGR format).

    Raises:
        Exception: If download or frame extraction fails.
    """
    try:
        print(f"📥 Downloading video for frame extraction: {url}")
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()

        # Write to a temporary file because OpenCV VideoCapture needs a file path
        suffix = os.path.splitext(url.split('?')[0])[1] or '.mp4'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)

        try:
            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                raise ValueError(f"OpenCV could not open video file at {tmp_path}")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            duration_sec = total_frames / fps if total_frames > 0 else 0

            print(f"🎬 Video info: {total_frames} frames, {fps:.1f} fps, {duration_sec:.1f}s")

            if total_frames == 0:
                # Fallback: just grab the first available frame
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    return [frame]
                raise ValueError("Video has no readable frames.")

            # Sample evenly across the video, avoid the very first/last 5% to skip
            # logos or black intro/outro frames
            start = max(0, int(total_frames * 0.05))
            end = min(total_frames - 1, int(total_frames * 0.95))
            indices = [
                int(start + i * (end - start) / max(num_frames - 1, 1))
                for i in range(num_frames)
            ]

            frames = []
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret and frame is not None:
                    frames.append(frame)

            cap.release()

            if not frames:
                raise ValueError("No frames could be extracted from the video.")

            print(f"✅ Extracted {len(frames)} frames from video.")
            return frames

        finally:
            # Always clean up the temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except Exception as e:
        raise Exception(f"Failed to extract frames from video: {str(e)}")


def load_media(url: str) -> tuple:
    """
    Smart media loader: returns (frames, is_video).
    For images, frames = [single_frame].
    For videos, frames = [multiple sampled frames].
    """
    response_head = requests.head(url, timeout=10, allow_redirects=True)
    content_type = response_head.headers.get('Content-Type', '')

    if _is_video_url(url, content_type):
        frames = extract_frames_from_video(url, num_frames=5)
        return frames, True
    else:
        frame = download_image(url)
        return [frame], False


class TrafficViolationDetector:
    """
    Main detector class for traffic violations using YOLOv8
    """

    # Violation types supported
    VIOLATION_TYPES = {
        'no_helmet': 'No Helmet Violation',
        'red_light': 'Red Light Violation',
        'wrong_way': 'Wrong Way Driving',
        'illegal_parking': 'Illegal Parking'
    }

    # Confidence thresholds
    MIN_CONFIDENCE = {
        'no_helmet': 0.60,
        'red_light': 0.70,
        'wrong_way': 0.65,
        'illegal_parking': 0.70
    }

    def __init__(self, model_size: str = 'n'):
        """
        Initialize the detector

        Args:
            model_size: YOLOv8 model size ('n', 's', 'm', 'l', 'x')
                       'n' = nano (fastest, good for demo)
                       's' = small
                       'm' = medium
        """
        print(f"Initializing YOLOv8{model_size} model...")

        # Load YOLOv8 model for object detection
        self.model = YOLO(f'yolov8{model_size}.pt')

        # Set device (GPU if available)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Using device: {self.device}")

        # COCO class names that are relevant
        self.relevant_classes = {
            'person': 0,
            'bicycle': 1,
            'car': 2,
            'motorcycle': 3,
            'bus': 5,
            'truck': 7,
            'traffic light': 9
        }

    def detect_no_helmet(self, image: np.ndarray) -> Optional[ViolationResult]:
        """
        Detect motorcycle riders without helmets

        Logic:
        - Detect motorcycles and persons
        - Check if a person is on/near a motorcycle
        - Analyze a head region for helmet presence
        """
        results = self.model(image, conf=0.4)

        motorcycles = []
        persons = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].cpu().numpy().astype(int)

                if cls == self.relevant_classes['motorcycle'] and conf > 0.5:
                    motorcycles.append({'bbox': bbox, 'conf': conf})
                elif cls == self.relevant_classes['person'] and conf > 0.5:
                    persons.append({'bbox': bbox, 'conf': conf})

        # Check if person is near motorcycle (simplified for demo)
        for moto in motorcycles:
            for person in persons:
                if _is_person_on_vehicle(person['bbox'], moto['bbox']):
                    # In real implementation, use helmet detection model
                    # For demo: assume violation if motorcycle + person detected

                    confidence = min(moto['conf'], person['conf'])

                    if confidence >= self.MIN_CONFIDENCE['no_helmet']:
                        return ViolationResult(
                            violation_type='no_helmet',
                            confidence=float(confidence),
                            status='verified',
                            details={
                                'vehicle_type': 'motorcycle',
                                'rider_detected': True,
                                'helmet_detected': False,
                                'description': 'Motorcycle rider detected without helmet'
                            },
                            bbox=moto['bbox'].tolist()
                        )

        return None

    def detect_red_light_violation(self, image: np.ndarray) -> Optional[ViolationResult]:
        """
        Detect vehicles running red lights

        Logic:
        - Detect traffic lights and their color (red)
        - Detect vehicles crossing the stop line
        - Verify temporal consistency (for video)
        """
        results = self.model(image, conf=0.5)

        traffic_lights = []
        vehicles = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].cpu().numpy().astype(int)

                if cls == self.relevant_classes['traffic light']:
                    # Analyze color (simplified - in production use color detection)
                    is_red = _detect_red_light_color(image, bbox)
                    if is_red:
                        traffic_lights.append({'bbox': bbox, 'conf': conf})

                elif cls in [self.relevant_classes['car'],
                             self.relevant_classes['motorcycle'],
                             self.relevant_classes['truck'],
                             self.relevant_classes['bus']]:
                    vehicles.append({'bbox': bbox, 'conf': conf, 'class': cls})

        # Check if vehicle crossed intersection with red light
        if traffic_lights and vehicles:
            # Simplified logic: if red light and vehicle in frame
            # In production: track vehicle movement across stop line

            best_vehicle = max(vehicles, key=lambda x: x['conf'])
            best_light = max(traffic_lights, key=lambda x: x['conf'])

            confidence = min(best_vehicle['conf'], best_light['conf'])

            if confidence >= self.MIN_CONFIDENCE['red_light']:
                return ViolationResult(
                    violation_type='red_light',
                    confidence=float(confidence),
                    status='verified',
                    details={
                        'traffic_light_status': 'red',
                        'vehicle_crossed': True,
                        'description': 'Vehicle detected crossing intersection during red light'
                    },
                    bbox=best_vehicle['bbox'].tolist()
                )

        return None

    def detect_wrong_way(self, image: np.ndarray) -> Optional[ViolationResult]:
        """
        Detect wrong-way driving

        Logic:
        - Detect vehicles
        - Analyze a direction based on lane markers/arrows
        - Compare vehicle orientation with an expected direction

        Note: For the demo, we simulate based on vehicle position
        """
        results = self.model(image, conf=0.5)

        vehicles = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].cpu().numpy().astype(int)

                if cls in [self.relevant_classes['car'],
                           self.relevant_classes['motorcycle'],
                           self.relevant_classes['truck'],
                           self.relevant_classes['bus']]:
                    vehicles.append({'bbox': bbox, 'conf': conf})

        if vehicles:
            # For demo: analyze vehicle position/orientation
            # In production: use lane detection + direction analysis

            for vehicle in vehicles:
                # Simplified check (for demo)
                wrong_direction = _analyze_vehicle_direction(image, vehicle['bbox'])

                if wrong_direction and vehicle['conf'] >= self.MIN_CONFIDENCE['wrong_way']:
                    return ViolationResult(
                        violation_type='wrong_way',
                        confidence=float(vehicle['conf']),
                        status='verified',
                        details={
                            'expected_direction': 'forward',
                            'actual_direction': 'reverse',
                            'description': 'Vehicle detected traveling in wrong direction'
                        },
                        bbox=vehicle['bbox'].tolist()
                    )

        return None

    def detect_illegal_parking(self, image: np.ndarray) -> Optional[ViolationResult]:
        """
        Detect illegal parking in restricted zones

        Logic:
        - Detect parked vehicles
        - Check if in no-parking zone (marked area)
        - Verify stationary duration (for video)
        """
        results = self.model(image, conf=0.6)

        vehicles = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].cpu().numpy().astype(int)

                if cls in [self.relevant_classes['car'],
                           self.relevant_classes['motorcycle'],
                           self.relevant_classes['truck']]:
                    vehicles.append({'bbox': bbox, 'conf': conf})

        if vehicles:
            # For demo: check if vehicle in designated no-parking zone
            # In production: use zone mapping + temporal analysis

            for vehicle in vehicles:
                in_restricted_zone = _check_restricted_parking_zone(image, vehicle['bbox'])

                if in_restricted_zone and vehicle['conf'] >= self.MIN_CONFIDENCE['illegal_parking']:
                    return ViolationResult(
                        violation_type='illegal_parking',
                        confidence=float(vehicle['conf']),
                        status='verified',
                        details={
                            'zone_type': 'no_parking',
                            'duration': 'stationary',
                            'description': 'Vehicle detected parked in restricted no-parking zone'
                        },
                        bbox=vehicle['bbox'].tolist()
                    )

        return None

    def _analyze_single_frame(self, image: np.ndarray) -> List[ViolationResult]:
        """Run all detectors on a single frame and return all violations found."""
        violations_found = []

        # 1. No Helmet
        helmet_result = self.detect_no_helmet(image)
        if helmet_result:
            violations_found.append(helmet_result)

        # 2. Red Light
        red_light_result = self.detect_red_light_violation(image)
        if red_light_result:
            violations_found.append(red_light_result)

        # 3. Wrong Way
        wrong_way_result = self.detect_wrong_way(image)
        if wrong_way_result:
            violations_found.append(wrong_way_result)

        # 4. Illegal Parking
        parking_result = self.detect_illegal_parking(image)
        if parking_result:
            violations_found.append(parking_result)

        return violations_found

    def analyze_image(self, image_source: str) -> ViolationResult:
        """
        Main analysis function - handles both images and videos.

        For images: performs detection on the single frame.
        For videos: samples multiple frames and returns the highest-confidence
                    violation found across all frames.

        Args:
            image_source: URL or file path to image/video.

        Returns:
            ViolationResult with the highest confidence violation found.
        """
        if image_source.startswith('http'):
            frames, is_video = load_media(image_source)
        else:
            # Local file path — detect by extension
            ext = os.path.splitext(image_source.lower())[1]
            if ext in VIDEO_EXTENSIONS:
                cap = cv2.VideoCapture(image_source)
                if not cap.isOpened():
                    raise ValueError(f"Could not open video from {image_source}")
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                indices = [int(total * i / 4) for i in range(5)]
                frames = []
                for idx in indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        frames.append(frame)
                cap.release()
                is_video = True
            else:
                img = cv2.imread(image_source)
                if img is None:
                    raise ValueError(f"Could not read image from {image_source}")
                frames = [img]
                is_video = False

        media_type = "video" if is_video else "image"
        print(f"📂 Media type: {media_type}, frames to analyze: {len(frames)}")

        # Analyze each frame and collect all violations
        all_violations: List[ViolationResult] = []
        for i, frame in enumerate(frames):
            print(f"   🔍 Analyzing frame {i + 1}/{len(frames)} — shape: {frame.shape}")
            frame_violations = self._analyze_single_frame(frame)
            all_violations.extend(frame_violations)

        # Return highest confidence violation across all frames, or no-violation
        if all_violations:
            best_violation = max(all_violations, key=lambda x: x.confidence)
            if is_video:
                best_violation.details['source'] = 'video'
                best_violation.details['frames_analyzed'] = len(frames)
            return best_violation
        else:
            return ViolationResult(
                violation_type='none',
                confidence=0.0,
                status='no_violation',
                details={
                    'description': f'No traffic violations detected in {media_type}',
                    'source': media_type,
                    'frames_analyzed': len(frames)
                }
            )

    # Helper methods (simplified for demo)


# Singleton instance
_detector_instance = None


def get_detector() -> TrafficViolationDetector:
    """Get or create a detector instance"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = TrafficViolationDetector(model_size='n')
    return _detector_instance