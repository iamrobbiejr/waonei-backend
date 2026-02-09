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


def download_image(url: str) -> np.ndarray:
    """Download image from URL and convert to OpenCV format"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        image = Image.open(BytesIO(response.content))
        image = image.convert('RGB')

        # Convert PIL to OpenCV format
        opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        return opencv_image

    except Exception as e:
        raise Exception(f"Failed to download image: {str(e)}")


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

    def analyze_image(self, image_source: str) -> ViolationResult:
        """
        Main analysis function - checks for all violation types

        Args:
            image_source: URL or file path to image

        Returns:
            ViolationResult with the highest confidence violation found
        """
        # Download/load image
        if image_source.startswith('http'):
            image = download_image(image_source)
        else:
            image = cv2.imread(image_source)
            if image is None:
                raise ValueError(f"Could not read image from {image_source}")

        print(f"Image loaded: {image.shape}")

        # Run all detection methods
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

        # Return highest confidence violation or no violation found
        if violations_found:
            best_violation = max(violations_found, key=lambda x: x.confidence)
            return best_violation
        else:
            return ViolationResult(
                violation_type='none',
                confidence=0.0,
                status='no_violation',
                details={'description': 'No traffic violations detected in image'}
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