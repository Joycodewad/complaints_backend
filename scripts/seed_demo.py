"""Données de démonstration pour tester tout le workflow.

    python -m scripts.seed_demo           # charge les données (sans doublon si déjà chargées)
    python -m scripts.seed_demo --reset   # supprime uniquement les données de démo
    python -m scripts.seed_demo --reload  # --reset puis rechargement

Le script complète `scripts.seed` (admin / coord / student) : il ajoute des départements, des catégories,
des étudiants, des coordinateurs et ~40 plaintes réparties sur tout le cycle de vie
(SUBMITTED -> ASSIGNED -> IN_PROGRESS -> RESOLVED -> CLOSED, avec réouvertures), leurs messages,
leur historique de statut et leurs notifications. Les plaintes de démo sont repérées par
`attachment = "demo-seed"` : le reset ne touche donc jamais aux données réelles.
Données entièrement fictives. Mot de passe de tous les comptes ajoutés : voir DEMO_PASSWORD.
"""
import random
import sys
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, func, select

from app.core.security import hash_password
from app.core.utils import utcnow
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    Category, Complaint, ComplaintComment, Department, Notification, Priority, Role, Status, StatusHistory, User,
)

MARKER = "demo-seed"
DEMO_PASSWORD = "Password123!"
S = Status

DEPARTMENTS = ["Engineering", "Sciences", "Business", "Humanities", "Library", "Hostel and facilities", "Finance office"]

CATEGORIES = {
    "Classroom infrastructure": "Projectors, chairs, lighting, air conditioning in teaching rooms.",
    "Facilities": "Water, electricity, stairwells, parking, accessibility.",
    "Sanitation": "Restrooms, cleaning, waste.",
    "Equipment": "Printers, lab computers, network, library equipment.",
    "Administrative services": "Fees, documents, registration, timetable errors.",
    "Other": "Anything that does not fit another category.",
}

# username, prénom, nom, matricule
STUDENTS = [
    ("amara.okafor", "Amara", "Okafor", "2026-04817"),
    ("kabelo.mthembu", "Kabelo", "Mthembu", "2026-03122"),
    ("lerato.dube", "Lerato", "Dube", "2025-09876"),
    ("thabo.nkosi", "Thabo", "Nkosi", "2025-07431"),
    ("zoe.martin", "Zoé", "Martin", "2026-01550"),
    ("noah.dlamini", "Noah", "Dlamini", "2024-05218"),
    ("lina.haddad", "Lina", "Haddad", "2026-02764"),
    ("omar.benali", "Omar", "Benali", "2025-04093"),
]

# username, prénom, nom, département
COORDINATORS = [
    ("priya.naidoo", "Priya", "Naidoo", "Engineering"),
    ("erik.lindqvist", "Erik", "Lindqvist", "Hostel and facilities"),
    ("grace.okafor", "Grace", "Okafor", "Library"),
    ("daniel.tan", "Daniel", "Tan", "Finance office"),
]

ADMINS = [("jordan.lee", "Jordan", "Lee")]

# catégorie -> coordinateur le plus pertinent
OWNER = {
    "Classroom infrastructure": "priya.naidoo",
    "Facilities": "erik.lindqvist",
    "Sanitation": "erik.lindqvist",
    "Equipment": "grace.okafor",
    "Administrative services": "daniel.tan",
    "Other": "grace.okafor",
}

# (titre, description, catégorie, étudiant, statut final, priorité, âge en jours, option)
# option : "reopened" = résolue puis rouverte ; "reopened-resolved" = rouverte puis re-résolue ;
#          "chat" = échange de messages ; "" = rien
C = [
    # --- SUBMITTED : en attente d'affectation (file de l'admin)
    ("Projector in Room B204 keeps flickering", "The projector flickers within ten minutes of being switched on, which makes slides hard to read. It happens in every lecture.", "Classroom infrastructure", "amara.okafor", S.SUBMITTED, None, 1, ""),
    ("Library printer jams on every second page", "The ground-floor printer jams almost every time you print more than two pages. Several of us lost printing credit.", "Equipment", "kabelo.mthembu", S.SUBMITTED, None, 2, "chat"),
    ("Stairwell lighting near the east entrance is unsafe", "Two of the three lights in the east stairwell do not work. It is very dark after 6 pm.", "Facilities", "lerato.dube", S.SUBMITTED, None, 1, ""),
    ("Restrooms in Block C not cleaned all week", "The first-floor restrooms in Block C are out of soap and paper towels and the bins were not emptied since Monday.", "Sanitation", "thabo.nkosi", S.SUBMITTED, None, 3, ""),
    ("Timetable shows two lectures at the same time", "On Thursdays my timetable lists Databases and Statistics at 10:00. I cannot attend both.", "Administrative services", "zoe.martin", S.SUBMITTED, None, 2, ""),
    ("Air conditioning too cold in Lecture Hall A2", "The air conditioning in A2 is set so low that students bring jackets in summer. Nobody can adjust it.", "Classroom infrastructure", "noah.dlamini", S.SUBMITTED, None, 4, ""),
    ("No wheelchair ramp at the Humanities building", "The only entrance to the Humanities building has steps. A classmate cannot reach the second-floor seminar room.", "Facilities", "lina.haddad", S.SUBMITTED, None, 1, ""),
    ("Student card does not open the library gate", "My new student card is rejected by the library turnstile. The card works at the cafeteria.", "Equipment", "omar.benali", S.SUBMITTED, None, 5, ""),
    ("Lab 2 computers are missing the statistics software", "None of the PCs in Lab 2 have R or the course packages, so we cannot do the practical sessions.", "Equipment", "amara.okafor", S.SUBMITTED, None, 2, ""),
    ("Cafeteria receipts not accepted for refunds", "I was told the finance office does not accept cafeteria receipts for the meal plan refund. The policy page says otherwise.", "Administrative services", "kabelo.mthembu", S.SUBMITTED, None, 3, ""),
    ("Broken window in the hostel corridor, floor 3", "A corridor window on the third floor of Hostel B does not close and rain comes in.", "Facilities", "lerato.dube", S.SUBMITTED, None, 6, ""),
    ("Request: extend library opening hours during exams", "The library closes at 8 pm during exam weeks. Many of us need a quiet place later.", "Other", "thabo.nkosi", S.SUBMITTED, None, 7, ""),
    # --- ASSIGNED : affectées, pas encore démarrées
    ("Water cooler on the second floor is out of order", "The cooler outside the Block A seminar rooms has had an out-of-order sign for two weeks.", "Facilities", "zoe.martin", S.ASSIGNED, Priority.MEDIUM, 8, ""),
    ("Fee statement shows a duplicate charge", "My October fee statement lists the lab fee twice. A screenshot is available on request.", "Administrative services", "noah.dlamini", S.ASSIGNED, Priority.HIGH, 6, "chat"),
    ("Chairs are broken in Lecture Hall A1", "At least eight chairs in the back rows have broken arms or loose seats.", "Classroom infrastructure", "lina.haddad", S.ASSIGNED, Priority.LOW, 9, ""),
    ("Wi-Fi drops every few minutes in the library", "The library Wi-Fi disconnects all the time on the second floor, which breaks online exams.", "Equipment", "omar.benali", S.ASSIGNED, Priority.URGENT, 4, ""),
    ("Leaking tap in the Block B restrooms", "A tap has been dripping non-stop for days and the floor is wet.", "Sanitation", "amara.okafor", S.ASSIGNED, Priority.MEDIUM, 5, ""),
    ("Whiteboard markers never available in B105", "There are never any markers in B105 and lecturers have to bring their own.", "Classroom infrastructure", "kabelo.mthembu", S.ASSIGNED, Priority.LOW, 10, ""),
    ("Late-night noise from the hostel common room", "The Hostel A common room is loud until 2 am on weekdays, which makes it hard to study.", "Facilities", "lerato.dube", S.ASSIGNED, Priority.MEDIUM, 7, ""),
    ("Transcript request pending for three weeks", "I requested an official transcript three weeks ago and it has not been issued.", "Administrative services", "thabo.nkosi", S.ASSIGNED, Priority.HIGH, 11, ""),
    # --- IN_PROGRESS : en cours de traitement
    ("Lab PCs keep losing their network connection", "In Lab 3 at least six PCs drop off the network every 20 minutes. Saved work on network drives gets locked.", "Equipment", "zoe.martin", S.IN_PROGRESS, Priority.URGENT, 12, "chat"),
    ("Parking lot lights out after 6 pm", "The lights in parking lot C stopped working, which is unsafe for evening classes.", "Facilities", "noah.dlamini", S.IN_PROGRESS, Priority.HIGH, 9, ""),
    ("Overflowing bins near the cafeteria", "The bins near the cafeteria entrance overflow by noon and attract insects.", "Sanitation", "lina.haddad", S.IN_PROGRESS, Priority.MEDIUM, 8, ""),
    ("Projector remote missing in Room C310", "There is no remote for the projector in C310, so lecturers cannot change inputs.", "Classroom infrastructure", "omar.benali", S.IN_PROGRESS, Priority.LOW, 10, ""),
    ("Scholarship payment not received", "My scholarship instalment for October has not reached my account although the portal says paid.", "Administrative services", "amara.okafor", S.IN_PROGRESS, Priority.URGENT, 6, "chat"),
    ("Broken scanner at the library desk", "The scanner at the library desk has been out of order for a month.", "Equipment", "kabelo.mthembu", S.IN_PROGRESS, Priority.MEDIUM, 14, "reopened"),
    # --- RESOLVED : résolues, à vérifier et clôturer par l'admin
    ("Heater not working in Lecture Hall B1", "The heater in B1 did not work during the cold week.", "Classroom infrastructure", "lerato.dube", S.RESOLVED, Priority.MEDIUM, 15, ""),
    ("Hot water missing in the Hostel B showers", "There was no hot water on the second floor of Hostel B all week.", "Facilities", "thabo.nkosi", S.RESOLVED, Priority.HIGH, 13, "chat"),
    ("Wrong grade displayed for Algorithms", "The portal shows 54 instead of 64 for my Algorithms midterm.", "Administrative services", "zoe.martin", S.RESOLVED, Priority.HIGH, 18, ""),
    ("Poor sound in the Auditorium", "The microphones in the auditorium crackle, nobody at the back can hear the lecturer.", "Classroom infrastructure", "noah.dlamini", S.RESOLVED, Priority.MEDIUM, 16, "reopened-resolved"),
    ("Dirty microwave in the student lounge", "The student lounge microwave has not been cleaned in weeks.", "Sanitation", "lina.haddad", S.RESOLVED, Priority.LOW, 12, ""),
    # --- CLOSED : terminées
    ("Duplicate charge on October fees", "My October fee statement listed the lab fee twice.", "Administrative services", "amara.okafor", S.CLOSED, Priority.HIGH, 30, ""),
    ("Broken chairs in Lecture Hall A3", "Several chairs in A3 had broken arms or loose seats.", "Classroom infrastructure", "kabelo.mthembu", S.CLOSED, Priority.MEDIUM, 34, "chat"),
    ("Printer out of toner in the Engineering lab", "The Engineering lab printer ran out of toner and nobody replaced it.", "Equipment", "omar.benali", S.CLOSED, Priority.LOW, 28, ""),
    ("Flooded restroom in Block A", "A pipe burst flooded the ground-floor restroom in Block A.", "Sanitation", "lerato.dube", S.CLOSED, Priority.URGENT, 25, ""),
    ("Library book catalogue is offline", "The online library catalogue returned an error for two days.", "Other", "thabo.nkosi", S.CLOSED, Priority.MEDIUM, 40, ""),
    ("Emergency exit blocked by furniture", "Stacked furniture blocked the emergency exit of Lecture Hall A1.", "Facilities", "zoe.martin", S.CLOSED, Priority.URGENT, 38, ""),
]

STUDENT_QUESTIONS = [
    "Any news on this? It is affecting several of us every day.",
    "Could someone give an estimated date for the fix?",
    "Just to add: the problem got worse this week.",
    "Thank you for looking into it. Please let me know if you need photos or more details.",
]
COORD_UPDATES = [
    "Thanks for reporting this. A technician has been scheduled to inspect it.",
    "We have ordered the replacement part. Delivery is expected within a few days.",
    "The supplier confirmed the intervention for early next week.",
    "We are checking the issue with the maintenance team and will update you tomorrow.",
]
RESOLUTIONS = [
    "The faulty part was replaced and the equipment tested. Everything works again.",
    "The issue is fixed. Please tell us if it comes back.",
    "The maintenance team completed the repair and checked it on site.",
    "The record was corrected and you will see the update on the portal within 24 hours.",
]
CLOSING_NOTES = ["Verified with the student. Closing the complaint.", "Fix confirmed. Closed."]


def _users(db) -> dict[str, User]:
    return {u.username: u for u in db.scalars(select(User)).all()}


def _get_or_create_departments(db) -> dict[str, Department]:
    existing = {d.name: d for d in db.scalars(select(Department)).all()}
    for name in DEPARTMENTS:
        if name not in existing:
            existing[name] = Department(name=name)
            db.add(existing[name])
    db.flush()
    return existing


def _get_or_create_categories(db) -> dict[str, Category]:
    existing = {c.name: c for c in db.scalars(select(Category)).all()}
    for name, desc in CATEGORIES.items():
        if name not in existing:
            existing[name] = Category(name=name, description=desc)
            db.add(existing[name])
    db.flush()
    return existing


def reset(db) -> None:
    """Supprime uniquement les données de démo (plaintes marquées + comptes ajoutés par ce script)."""
    ids = db.scalars(select(Complaint.id).where(Complaint.attachment == MARKER)).all()
    if ids:
        db.execute(delete(Notification).where(Notification.complaint_id.in_(ids)))
        db.execute(delete(ComplaintComment).where(ComplaintComment.complaint_id.in_(ids)))
        db.execute(delete(StatusHistory).where(StatusHistory.complaint_id.in_(ids)))
        db.execute(delete(Complaint).where(Complaint.id.in_(ids)))
    names = [u[0] for u in STUDENTS] + [u[0] for u in COORDINATORS] + [a[0] for a in ADMINS]
    uids = db.scalars(select(User.id).where(User.username.in_(names))).all()
    if uids:
        db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
        # un compte de démo qui aurait écrit sur une plainte réelle ne doit pas être supprimé
        used = set(db.scalars(select(Complaint.student_id).where(Complaint.student_id.in_(uids))).all())
        used |= set(db.scalars(select(Complaint.assigned_to_id).where(Complaint.assigned_to_id.in_(uids))).all())
        used |= set(db.scalars(select(ComplaintComment.author_id).where(ComplaintComment.author_id.in_(uids))).all())
        used |= set(db.scalars(select(StatusHistory.changed_by_id).where(StatusHistory.changed_by_id.in_(uids))).all())
        db.execute(delete(User).where(User.id.in_([i for i in uids if i not in used])))
    db.commit()
    print(f"Demo data removed ({len(ids)} complaints).")


def load(db) -> None:
    if db.scalar(select(Complaint.id).where(Complaint.attachment == MARKER).limit(1)):
        print("Demo data already loaded (use --reload to reset and load again).")
        return

    rng = random.Random(42)  # données déterministes
    now = utcnow()
    pwd = hash_password(DEMO_PASSWORD)
    depts = _get_or_create_departments(db)
    cats = _get_or_create_categories(db)

    users = _users(db)  # comptes de démo conservés par un précédent reset : on les réutilise
    new_users = []
    for username, first, last, sid in STUDENTS:
        new_users.append(User(username=username, email=f"{username}@univ.edu", hashed_password=pwd, role=Role.STUDENT,
                              first_name=first, last_name=last, student_id=sid))
    for username, first, last, dept in COORDINATORS:
        new_users.append(User(username=username, email=f"{username}@univ.edu", hashed_password=pwd,
                              role=Role.COORDINATOR, first_name=first, last_name=last, department_id=depts[dept].id))
    for username, first, last in ADMINS:
        new_users.append(User(username=username, email=f"{username}@univ.edu", hashed_password=pwd,
                              role=Role.ADMIN, first_name=first, last_name=last))
    db.add_all([u for u in new_users if u.username not in users])
    db.flush()
    users = _users(db)
    admins = [u for u in users.values() if u.role == Role.ADMIN and u.is_active]

    year_counter: dict[int, int] = defaultdict(int)
    for year in {(now - timedelta(days=c[6])).year for c in C} | {now.year}:
        last = db.scalar(select(func.max(Complaint.reference)).where(Complaint.reference.like(f"CMP-{year}-%")))
        year_counter[year] = int(last.rsplit("-", 1)[1]) if last else 0

    def notify(user, complaint, message, when, read):
        if user is not None:
            db.add(Notification(user_id=user.id, complaint_id=complaint.id, message=message, created_at=when, is_read=read))

    created = 0
    for title, desc, cat, stud, final, prio, age, opt in C:
        student = users[stud]
        owner = users[OWNER[cat]]
        admin = rng.choice(admins)
        t0 = now - timedelta(days=age, hours=rng.randint(0, 6), minutes=rng.randint(0, 59))
        year_counter[t0.year] += 1
        c = Complaint(
            reference=f"CMP-{t0.year}-{year_counter[t0.year]:04d}", title=title, description=desc,
            category_id=cats[cat].id, student_id=student.id, status=S.SUBMITTED, priority=None,
            attachment=MARKER, created_at=t0, updated_at=t0,
        )
        db.add(c)
        db.flush()

        history: list[tuple[Status | None, Status, User, object]] = [(None, S.SUBMITTED, student, t0)]
        last_change = t0

        def read_flag(when):  # les notifications anciennes sont lues, les récentes non
            return (now - when) > timedelta(days=2) or rng.random() < 0.2

        for a in admins:
            notify(a, c, f"New complaint {c.reference}: {title}", t0, read_flag(t0))

        def step(new, actor, when, assignee_notify=True):
            nonlocal last_change
            old = c.status
            c.status = new
            history.append((old, new, actor, when))
            last_change = when
            msg = f"Complaint {c.reference}: {old.value} -> {new.value}"
            notify(student, c, msg, when, read_flag(when))
            if c.assigned_to_id and assignee_notify and c.assigned_to_id != actor.id:
                notify(users_by_id[c.assigned_to_id], c, msg, when, read_flag(when))

        users_by_id = {u.id: u for u in users.values()}

        def comment(author, message, when, resolution=False):
            nonlocal last_change
            db.add(ComplaintComment(complaint_id=c.id, author_id=author.id, message=message,
                                    is_resolution=resolution, created_at=when))
            target = c.assigned_to_id and users_by_id[c.assigned_to_id] if author.id == student.id else student
            notify(target, c, f"New message on {c.reference}", when, read_flag(when))
            last_change = max(last_change, when)

        def clamp(when):  # jamais dans le futur
            return min(when, now - timedelta(minutes=5))

        if final != S.SUBMITTED:
            t1 = clamp(t0 + timedelta(hours=rng.randint(3, 20)))
            c.assigned_to_id = owner.id
            c.priority = prio
            notify(owner, c, f"Complaint {c.reference} has been assigned to you", t1, read_flag(t1))
            step(S.ASSIGNED, admin, t1)

        if final in (S.IN_PROGRESS, S.RESOLVED, S.CLOSED):
            t2 = clamp(last_change + timedelta(hours=rng.randint(10, 30)))
            step(S.IN_PROGRESS, owner, t2)
            if opt in ("chat", "reopened"):
                comment(owner, rng.choice(COORD_UPDATES), clamp(t2 + timedelta(hours=2)))

        if opt == "chat":
            base = clamp(t0 + timedelta(hours=rng.randint(1, 8)))
            comment(student, rng.choice(STUDENT_QUESTIONS), base)

        if final in (S.RESOLVED, S.CLOSED) or opt == "reopened":
            t3 = clamp(last_change + timedelta(days=rng.randint(1, 3), hours=rng.randint(0, 6)))
            comment(owner, rng.choice(RESOLUTIONS), t3, resolution=True)
            step(S.RESOLVED, owner, t3)
            c.resolved_at = t3

        if opt in ("reopened", "reopened-resolved"):
            t4 = clamp(last_change + timedelta(hours=rng.randint(6, 30)))
            comment(student, "The problem is back, it is not fixed.", t4)
            step(S.IN_PROGRESS, admin, t4)
            c.resolved_at = None
            if opt == "reopened-resolved":
                t5 = clamp(last_change + timedelta(days=1))
                comment(owner, "We fixed the root cause this time and tested it with the room staff.", t5, resolution=True)
                step(S.RESOLVED, owner, t5)
                c.resolved_at = t5

        if final == S.CLOSED:
            t6 = clamp(last_change + timedelta(days=rng.randint(1, 3)))
            comment(admin, rng.choice(CLOSING_NOTES), t6)
            step(S.CLOSED, admin, t6)
            c.closed_at = t6

        assert c.status == final, (title, c.status, final)
        c.updated_at = last_change
        for old, new, actor, when in history:
            db.add(StatusHistory(complaint_id=c.id, old_status=old, new_status=new, changed_by_id=actor.id, changed_at=when))
        created += 1

    db.commit()
    print(f"OK: {created} demo complaints, {len(STUDENTS)} students, {len(COORDINATORS)} coordinators, "
          f"{len(ADMINS)} admin, {len(DEPARTMENTS)} departments, {len(CATEGORIES)} categories.")
    print(f"\nAccounts added by this script (password: {DEMO_PASSWORD}):")
    for u in STUDENTS:
        print(f"  student      {u[0]}")
    for u in COORDINATORS:
        print(f"  coordinator  {u[0]:<16} ({u[3]})")
    for u in ADMINS:
        print(f"  admin        {u[0]}")
    print("\nAccounts from scripts.seed (password admin123): admin, coord, student")


def main(argv: list[str]) -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if "--reset" in argv or "--reload" in argv:
            reset(db)
        if "--reset" not in argv:
            load(db)


if __name__ == "__main__":
    main(sys.argv[1:])
