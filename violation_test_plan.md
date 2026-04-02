# Manual Test Plan: Office-Based Traffic Violations

Since you are developing locally, this plan focuses on simulating the 4 supported violations using digital screens, physical props, and the newly added "Pick from Gallery" feature.

## Preparation

- **Download Sample Images**: Use the [Kaggle](https://www.kaggle.com/datasets) or [Roboflow](https://universe.roboflow.com/) sources mentioned in the plan.
- **Set Up Props**: (Optional for live camera testing) A motorcycle helmet, a toy car, and a large monitor.
- **Backend Ready**: Ensure `python app/main.py`, `redis`, and `celery -A app.worker worker` are all running.

---

## 1. No Helmet Violation

### Scenario A: Gallery Selection (Recommended)
1.  **Select**: Choose a high-res image of a motorcycle rider without a helmet from your phone's gallery.
2.  **Submit**: Fill in dummy vehicle details (e.g., "Silver Bike", "ABC-123").
3.  **Verify**: In the backend logs/UI, ensure the detector returns `violation_type: no_helmet` with confidence > 0.60.

### Scenario B: Live Office Capture
1.  **Setting**: Sit on a chair (facing away from the desk like on a bike) without a helmet.
2.  **Capture**: Use the app to take a photo of yourself.
3.  **Verify**: AI should flag "No Helmet". (Wear a helmet in the next test to verify "No Violation").

---

## 2. Red Light Violation

### Scenario A: YouTube Simulation
1.  **Setup**: Open a YouTube video of a busy intersection with a red light on your monitor.
2.  **Action**: Hold a toy car (or a phone showing a car) in front of the monitor and move it across the red light signal.
3.  **Capture**: Take a short 3-5 second video using the app.
4.  **Verify**: Ensure the backend's `detect_red_light_color` finds the red pixels and flags the violation.

---

## 3. Wrong Way Driving

### Scenario A: Desktop Lane Marking
1.  **Setup**: Use white tape or strips of paper to create "lanes" on your desk. Print a large "One Way" arrow.
2.  **Action**: Move a toy car in the direction opposite to the arrow.
3.  **Capture**: Take a photo or short video while the car is moving.
4.  **Verify**: The backend detector (which uses random 20% simulation for demo purposes) should eventually flag `wrong_way`.

---

## 4. Illegal Parking

### Scenario A: Restricted Zone Layout
1.  **Setup**: Use a printed "No Parking" sign or mark a 30% region on your monitor as a "Restricted Zone".
2.  **Action**: Place a model car inside that specific region.
3.  **Capture**: Take a photo.
4.  **Verify**: The backend `_check_restricted_parking_zone` logic (which checks if vehicle center_x < 30% of width) should trigger `illegal_parking`.

---

## Verification Checklist

| Violation Type | App Status | Backend Confidence | AI Correct? |
| :--- | :--- | :--- | :--- |
| **No Helmet** | Pending -> Verified | e.g. 0.85 | [ ] |
| **Red Light** | Pending -> Verified | e.g. 0.72 | [ ] |
| **Wrong Way** | Pending -> Verified | e.g. 0.65 | [ ] |
| **Parking** | Pending -> Verified | e.g. 0.90 | [ ] |

> [!TIP]
> Use the **Admin Dashboard** (at `http://localhost:5173/admin` if running frontend) to see real-time verification status and confidence scores.
