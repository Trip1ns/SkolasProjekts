// ==================== KONSULTĀCIJU KALENDĀRS ====================

// Rāda paziņojuma logu
function showMessage(text, type = "info") {
  const pazinotajs = document.getElementById("message-area");
  if (!pazinotajs) return;
  
  pazinotajs.innerHTML = `<div class="message message-${type}">${text}</div>`;
  pazinotajs.scrollIntoView({ behavior: "smooth", block: "nearest" });
  
  // Automātiski noslēpt pēc 5 sekundēm
  setTimeout(() => {
    pazinotajs.innerHTML = "";
  }, 5000);
}

// Ielādē pieejamos konsultāciju laikus
async function loadSlots() {
  const kalendars = document.getElementById("calendar");
  const ielades_zinotajs = document.getElementById("loading");
  if (!kalendars) return;

  if (ielades_zinotajs) ielades_zinotajs.style.display = "block";
  kalendars.innerHTML = "";

  try {
    const skolotajs_filtr = document.getElementById("teacher-filter");
    const diena_filtr = document.getElementById("day-filter");
    
    let url = "/api/slots";
    const parametri = [];
    if (skolotajs_filtr && skolotajs_filtr.value) {
      parametri.push("teacher_id=" + encodeURIComponent(skolotajs_filtr.value));
    }
    if (diena_filtr && diena_filtr.value) {
      parametri.push("day=" + encodeURIComponent(diena_filtr.value));
    }
    if (parametri.length > 0) {
      url += "?" + parametri.join("&");
    }

    const atbilde = await fetch(url);
    if (!atbilde.ok) {
      throw new Error("Kļūda ielādējot konsultācijas");
    }
    const dati = await atbilde.json();

    // Pielietojam nedēļas dienas filtru
    let filtris_dati = dati;
    if (diena_filtr && diena_filtr.value) {
      filteredData = data.filter(s => s.day === daySel.value);
    }

    // Group by subject (and then by teacher within subject)
    const slotsBySubject = {};
    filteredData.forEach(s => {
      const subject = s.teacher_subject || "Cits";
      if (!slotsBySubject[subject]) {
        slotsBySubject[subject] = {};
      }
      if (!slotsBySubject[subject][s.teacher]) {
        slotsBySubject[subject][s.teacher] = [];
      }
      slotsBySubject[subject][s.teacher].push(s);
    });

    if (Object.keys(slotsBySubject).length === 0) {
      calendar.innerHTML = '<div class="no-slots">Nav pieejamu konsultāciju ar izvēlētajiem filtriem.</div>';
      if (loading) loading.style.display = "none";
      return;
    }

    // Sakārtot pēc priekšmeta
    Object.keys(slotsBySubject).sort().forEach(subject => {
      const subjectSection = document.createElement("div");
      subjectSection.className = "subject-section";
      subjectSection.innerHTML = `<h4 class="subject-header">${subject}</h4>`;
      
      // Sakārtot pēc priekšmeta skolotāja
      Object.keys(slotsBySubject[subject]).sort().forEach(teacherName => {
        const teacherSection = document.createElement("div");
        teacherSection.className = "teacher-section";
        teacherSection.innerHTML = `<h5 class="teacher-name-header">👨‍🏫 ${teacherName}</h5>`;
        
        const teacherSlots = document.createElement("div");
        teacherSlots.className = "calendar-grid";

        // Sakārtot pēc dienas un laika
        const dayOrder = ["Pirmdiena", "Otrdiena", "Trešdiena", "Ceturtdiena", "Piektdiena"];
        slotsBySubject[subject][teacherName].sort((a, b) => {
          const dayA = dayOrder.indexOf(a.day);
          const dayB = dayOrder.indexOf(b.day);
          if (dayA !== dayB) {
            return dayA - dayB;
          }
          const timeA = a.time.split("-")[0].trim();
          const timeB = b.time.split("-")[0].trim();
          return timeA.localeCompare(timeB);
        });

        slotsBySubject[subject][teacherName].forEach(s => {
          const div = document.createElement("div");
          let classes = "slot";
          
          if (s.free <= 0) {
            classes += " full";
          }
          if (s.is_closed) {
            classes += " closed";
          }
          if (s.is_requested) {
            classes += " requested";
            if (s.request_status === "accepted") {
              classes += " accepted";
            } else if (s.request_status === "pending") {
              classes += " pending";
            }
          }

          div.className = classes;

          let statusBadge = "";
          if (s.is_requested) {
            if (s.request_status === "accepted") {
              statusBadge = '<span class="badge badge-accepted">✓ Apstiprināts</span>';
            } else if (s.request_status === "pending") {
              statusBadge = '<span class="badge badge-pending">⏳ Gaida</span>';
            }
          }

          div.innerHTML = `
            <div class="slot-header">
              <div class="slot-day-time">${s.day}, ${s.time}</div>
              ${statusBadge}
            </div>
            <div class="slot-room">🏢 ${s.room}</div>
            <div class="slot-free">Brīvas vietas: ${s.free}/${s.max_students || 10}</div>
          `;

          // Atļaut tikai skolēniem pieteikties
          const isStudent = (typeof window !== 'undefined' && window.currentUserRole === 'student');
          if (isStudent && s.free > 0 && !s.is_requested && !s.is_closed) {
            div.onclick = () => requestSlot(s);
            div.style.cursor = "pointer";
          } else if (s.is_requested) {
            div.style.cursor = "default";
          } else {
            div.style.cursor = "not-allowed";
          }

          teacherSlots.appendChild(div);
        });

        teacherSection.appendChild(teacherSlots);
        subjectSection.appendChild(teacherSection);
      });

      calendar.appendChild(subjectSection);
    });
  } catch (error) {
    console.error("Error loading slots:", error);
    showMessage("Kļūda ielādējot konsultācijas: " + error.message, "error");
    calendar.innerHTML = '<div class="error">Kļūda ielādējot konsultācijas.</div>';
  } finally {
    if (loading) loading.style.display = "none";
  }
}

async function requestSlot(slot) {
  // Pārbaude, vai laiks ir slēgts
  if (slot.is_closed) {
    showMessage("🔒 Šīs konsultācijas reģistrācija ir slēgta (30 min pirms sākuma)", "error");
    return;
  }
  

  openRequestModal(slot);
}


function openRequestModal(slot) {
  const modal = document.getElementById("request-modal");
  const backdrop = document.getElementById("modal-backdrop");
  
  if (!modal || !backdrop) return;
  
  // Aizpilda informāciju
  document.getElementById("modal-teacher").textContent = slot.teacher;
  document.getElementById("modal-day").textContent = slot.day;
  document.getElementById("modal-date").textContent = slot.date;
  document.getElementById("modal-time").textContent = slot.time;
  document.getElementById("modal-room").textContent = slot.room;
  document.getElementById("modal-free").textContent = `${slot.free}/${slot.max_students || 10}`;
  
  
  document.getElementById("request-reason").value = "";
  document.getElementById("char-count").textContent = "0";
  
  // Saglabāt slot info globālā mainīgajā (lai to varētu izmantot submitRequest)
  window.currentSlot = slot;
  
  modal.classList.remove("hidden");
  backdrop.classList.remove("hidden");
  
  setTimeout(() => {
    document.getElementById("request-reason").focus();
  }, 100);
}

function closeRequestModal() {
  const modal = document.getElementById("request-modal");
  const backdrop = document.getElementById("modal-backdrop");
  
  if (!modal || !backdrop) return;
  
  modal.classList.add("hidden");
  backdrop.classList.add("hidden");
  window.currentSlot = null;
}

// Iesniedz pieteikumu
async function submitRequest() {
  if (!window.currentSlot) {
    showMessage("Kļūda: slot informācija nav atrasta", "error");
    return;
  }
  
  const reason = document.getElementById("request-reason").value.trim();
  
  if (!reason) {
    showMessage("Lūdzu, norādiet iemeslu!", "error");
    return;
  }
  
  if (reason.length > 200) {
    showMessage("Iemesls pārāk garš (maks 200 znaki)", "error");
    return;
  }
  
  const submitBtn = document.getElementById("submit-request-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Sūta...";
  
  try {
    const res = await fetch("/api/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot_id: window.currentSlot.id,
        teacher_id: window.currentSlot.teacher_id,
        reason: reason
      })
    });

    const data = await res.json();

    if (!res.ok) {
      showMessage(data.error || "Kļūda nosūtot pieteikumu", "error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Pieteikties";
      return;
    }

    showMessage("✅ " + (data.message || "Pieteikums veiksmīgi nosūtīts!"), "success");
    closeRequestModal();
    loadSlots();
    loadStudentRequests();
  } catch (error) {
    console.error("Error making request:", error);
    showMessage("Kļūda nosūtot pieteikumu", "error");
    submitBtn.disabled = false;
    submitBtn.textContent = "Pieteikties";
  }
}

// Character counter
document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("request-reason");
  const charCount = document.getElementById("char-count");
  
  if (textarea && charCount) {
    textarea.addEventListener("input", () => {
      charCount.textContent = textarea.value.length;
      if (textarea.value.length > 200) {
        textarea.value = textarea.value.substring(0, 200);
        charCount.textContent = "200";
      }
    });
  }

  // Character counter for consultation notes
  const notesTextarea = document.getElementById("consultation-notes");
  const notesCharCount = document.getElementById("notes-char-count");
  
  if (notesTextarea && notesCharCount) {
    notesTextarea.addEventListener("input", () => {
      notesCharCount.textContent = notesTextarea.value.length;
      if (notesTextarea.value.length > 500) {
        notesTextarea.value = notesTextarea.value.substring(0, 500);
        notesCharCount.textContent = "500";
      }
    });
  }
});

async function loadStudentRequests() {
  const container = document.getElementById("my-requests");
  if (!container) return;

  try {
    const res = await fetch("/api/student/requests");
    if (!res.ok) {
      throw new Error("Kļūda ielādējot pieteikumus");
    }
    const data = await res.json();

    if (data.length === 0) {
      container.innerHTML = '<div class="no-requests">Jums nav neviena pieteikuma.</div>';
      return;
    }

    container.innerHTML = "";
    data.forEach(req => {
      const div = document.createElement("div");
      div.className = `request-card request-${req.status}`;
      
      let statusText = "";
      let statusClass = "";
      if (req.status === "accepted") {
        statusText = "✓ Apstiprināts";
        statusClass = "status-accepted";
      } else if (req.status === "pending") {
        statusText = "⏳ Gaida";
        statusClass = "status-pending";
      } else if (req.status === "rejected") {
        statusText = "✗ Noraidīts";
        statusClass = "status-rejected";
      }

      let cancelBtn = "";
      if (req.status === "pending") {
        cancelBtn = `<button onclick="cancelRequest(${req.id})" class="btn-cancel">Atcelt</button>`;
      }

      let consultationNotesText = "";
      if (req.consultation_notes) {
        consultationNotesText = `<div class="consultation-notes">
          <strong>📝 Skolotāja piezīmes:</strong>
          <div>${req.consultation_notes}</div>
        </div>`;
      }

      div.innerHTML = `
        <div class="request-header">
          <div>
            <strong>${req.teacher}</strong>
            <div class="request-meta">${req.day}, ${req.time} • 🏢 ${req.room}</div>
          </div>
          <span class="status-badge ${statusClass}">${statusText}</span>
        </div>
        <div class="request-reason">${req.reason || "(Nav iemesla)"}</div>
        ${req.reject_reason ? `<div class="reject-reason">Noraidīšanas iemesls: ${req.reject_reason}</div>` : ""}
        ${consultationNotesText}
        ${cancelBtn}
      `;
      container.appendChild(div);
    });
  } catch (error) {
    console.error("Error loading requests:", error);
    container.innerHTML = '<div class="error">Kļūda ielādējot pieteikumus.</div>';
  }
}

async function cancelRequest(requestId) {
  if (!confirm("Vai tiešām vēlaties atcelt šo pieteikumu?")) {
    return;
  }

  try {
    const res = await fetch("/api/student/cancel-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: requestId })
    });

    const data = await res.json();

    if (!res.ok) {
      showMessage(data.error || "Kļūda atceļot pieteikumu", "error");
      return;
    }

    showMessage(data.message || "Pieteikums atcelts", "success");
    loadSlots();
    loadStudentRequests();
  } catch (error) {
    console.error("Error canceling request:", error);
    showMessage("Kļūda atceļot pieteikumu", "error");
  }
}

async function loadTeachersForStudent() {
  try {
    const res = await fetch("/api/teachers");
    if (!res.ok) {
      throw new Error("Kļūda ielādējot skolotājus");
    }
    const data = await res.json();

    const sel = document.getElementById("teacher-filter");
    const list = document.getElementById("teacher-list");

    if (sel) {
      sel.innerHTML = '<option value="">Visi skolotāji</option>';
      data.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.name;
        sel.appendChild(opt);
      });
    }

    if (list) {
      list.innerHTML = "";
      if (data.length === 0) {
        list.innerHTML = '<div class="no-teachers">Nav skolotāju.</div>';
        return;
      }
      
      
      const teachersBySubject = {};
      data.forEach(t => {
        const subject = t.subject || "Cits";
        if (!teachersBySubject[subject]) {
          teachersBySubject[subject] = [];
        }
        teachersBySubject[subject].push(t);
      });

      
      Object.keys(teachersBySubject).sort().forEach(subject => {
        const subjectDiv = document.createElement("div");
        subjectDiv.className = "subject-group";
        subjectDiv.innerHTML = `<h5 class="subject-title">${subject}</h5>`;
        
        const teachersGrid = document.createElement("div");
        teachersGrid.className = "teacher-list-grid";
        
        teachersBySubject[subject].forEach(t => {
          const d = document.createElement("div");
          d.className = "teacher-item";
          d.textContent = t.name;
          d.style.cursor = "pointer";
          d.addEventListener("click", () => { 
            if (sel) { 
              sel.value = t.id; 
              loadSlots(); 
            } 
          });
          teachersGrid.appendChild(d);
        });
        
        subjectDiv.appendChild(teachersGrid);
        list.appendChild(subjectDiv);
      });
    }
  } catch (error) {
    console.error("Error loading teachers:", error);
  }
}


//  SKOLOTĀJU – PIETEIKUMI 
 
function showTeacherMessage(text, type = "info") {
  const msgArea = document.getElementById("message-area");
  if (!msgArea) return;
  
  msgArea.innerHTML = `<div class="message message-${type}">${text}</div>`;
  setTimeout(() => {
    msgArea.innerHTML = "";
  }, 5000);
}

async function loadTeacherRequests() {
  const box = document.getElementById("requests");
  const loading = document.getElementById("loading");
  if (!box) return;

  if (loading) loading.style.display = "block";
  box.innerHTML = "";

  try {
    const res = await fetch("/api/teacher/requests");
    if (!res.ok) {
      throw new Error("Kļūda ielādējot pieteikumus");
    }
    const data = await res.json();

    const filter = document.getElementById("filter")?.value || "all";
    const filtered = data.filter(r => filter === "all" || r.status === filter);

    if (filtered.length === 0) {
      box.innerHTML = '<div class="no-requests">Nav pieteikumu ar izvēlēto filtru.</div>';
      if (loading) loading.style.display = "none";
      return;
    }

    filtered.forEach(r => {
      const div = document.createElement("div");
      div.className = `request-card request-${r.status}`;

      let statusText = "";
      let statusClass = "";
      if (r.status === "accepted") {
        statusText = "✓ Apstiprināts";
        statusClass = "status-accepted";
      } else if (r.status === "pending") {
        statusText = "⏳ Gaida";
        statusClass = "status-pending";
      } else if (r.status === "rejected") {
        statusText = "✗ Noraidīts";
        statusClass = "status-rejected";
      }

      let actionButtons = "";
      if (r.status === "pending") {
        actionButtons = `
          <div style="margin-top: 12px; display: flex; gap: 10px;">
            <button onclick="decide(${r.id}, 'accepted')" class="btn-accept">Pieņemt</button>
            <button onclick="reject(${r.id})" class="btn-reject">Noraidīt</button>
          </div>
        `;
      }

      let consultationNotesText = "";
      if (r.consultation_notes) {
        consultationNotesText = `<div class="consultation-notes">
          <strong>📝 Piezīmes:</strong>
          <div>${r.consultation_notes}</div>
        </div>`;
      }

      div.innerHTML = `
        <div class="request-header">
          <div>
            <strong>${r.student}</strong>
            <div class="request-meta">${r.day}, ${r.time} • 🏢 ${r.room}</div>
          </div>
          <span class="status-badge ${statusClass}">${statusText}</span>
        </div>
        <div class="request-reason">${r.reason || "(Nav iemesla)"}</div>
        ${r.reject_reason ? `<div class="reject-reason">Noraidīšanas iemesls: ${r.reject_reason}</div>` : ""}
        ${consultationNotesText}
        ${actionButtons}
      `;

      box.appendChild(div);
    });
  } catch (error) {
    console.error("Error loading requests:", error);
    box.innerHTML = '<div class="error">Kļūda ielādējot pieteikumus.</div>';
  } finally {
    if (loading) loading.style.display = "none";
  }
}

async function decide(id, status) {
  // Akceptēšana
  if (status === "accepted") {
    window.pendingDecisionId = id;
    openNotesModal();
    return;
  }


  completeDecision(id, status, "");
}

function openNotesModal() {
  const modal = document.getElementById("consultation-notes-modal");
  const backdrop = document.getElementById("notes-modal-backdrop");
  if (!modal || !backdrop) return;

  document.getElementById("consultation-notes").value = "";
  document.getElementById("notes-char-count").textContent = "0";

  modal.classList.remove("hidden");
  backdrop.classList.remove("hidden");

  setTimeout(() => {
    document.getElementById("consultation-notes").focus();
  }, 100);
}

function closeNotesModal() {
  const modal = document.getElementById("consultation-notes-modal");
  const backdrop = document.getElementById("notes-modal-backdrop");
  if (!modal || !backdrop) return;

  modal.classList.add("hidden");
  backdrop.classList.add("hidden");
  window.pendingDecisionId = null;
}

async function confirmConsultationNotes() {
  const notes = document.getElementById("consultation-notes").value.trim();
  const id = window.pendingDecisionId;

  if (!id) {
    showTeacherMessage("Kļūda: pieteikums nav atrasts", "error");
    return;
  }

  closeNotesModal();
  completeDecision(id, "accepted", notes);
}

async function completeDecision(id, status, consultationNotes = "") {
  try {
    const res = await fetch("/api/teacher/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id,
        status,
        consultation_notes: consultationNotes || undefined
      })
    });

    const data = await res.json();
    if (!res.ok) {
      showTeacherMessage(data.error || "Kļūda", "error");
      return;
    }

    showTeacherMessage("Pieteikums apstiprināts!", "success");
    loadTeacherRequests();
  } catch (error) {
    console.error("Error deciding:", error);
    showTeacherMessage("Kļūda apstrādājot pieteikumu", "error");
  }
}

async function reject(id) {
  const reason = prompt("Noraidīšanas iemesls:");
  if (!reason || reason.trim() === "") {
    return;
  }

  try {
    const res = await fetch("/api/teacher/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id,
        status: "rejected",
        reason: reason.trim()
      })
    });

    const data = await res.json();
    if (!res.ok) {
      showTeacherMessage(data.error || "Kļūda", "error");
      return;
    }

    showTeacherMessage("Pieteikums noraidīts", "info");
    loadTeacherRequests();
  } catch (error) {
    console.error("Error rejecting:", error);
    showTeacherMessage("Kļūda apstrādājot pieteikumu", "error");
  }
}


// ADMIN SKATS – SKOLOTĀJI 

async function loadTeachersForAdmin() {
  const res = await fetch("/api/admin/teachers");
  const data = await res.json();

  const sel = document.getElementById("slot-teacher");
  if (!sel) return;

  sel.innerHTML = "";
  data.forEach(t => {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.name;
    sel.appendChild(opt);
  });
}

function showAdminMessage(text, type = "info") {
  const msgArea = document.getElementById("message-area");
  if (!msgArea) return;
  
  msgArea.innerHTML = `<div class="message message-${type}">${text}</div>`;
  setTimeout(() => {
    msgArea.innerHTML = "";
  }, 5000);
}

async function addSlot() {
  const teacherId = document.getElementById("slot-teacher").value;
  const day = document.getElementById("slot-day").value;
  const time = document.getElementById("slot-time").value;
  const room = document.getElementById("slot-room").value;
  const maxStudents = document.getElementById("slot-max").value;

  if (!teacherId || !day || !time || !room) {
    showAdminMessage("Lūdzu, aizpildiet visus laukus", "error");
    return;
  }

  try {
    const res = await fetch("/api/admin/add-slot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: teacherId,
        day: day,
        time: time,
        room: room,
        max_students: parseInt(maxStudents) || 10
      })
    });

    const data = await res.json();
    if (!res.ok) {
      showAdminMessage(data.error || "Kļūda pievienojot konsultācijas laiku", "error");
      return;
    }

    showAdminMessage("Konsultācijas laiks veiksmīgi pievienots!", "success");

    document.getElementById("slot-time").value = "";
    document.getElementById("slot-room").value = "";
    document.getElementById("slot-max").value = "10";
    loadAdminSlots();
    loadStats();
  } catch (error) {
    console.error("Error adding slot:", error);
    showAdminMessage("Kļūda pievienojot konsultācijas laiku", "error");
  }
}

async function loadAdminSlots() {
  const container = document.getElementById("slots-list");
  if (!container) return;

  try {
    const res = await fetch("/api/admin/slots");
    if (!res.ok) {
      throw new Error("Kļūda ielādējot konsultācijas");
    }
    const data = await res.json();

    if (data.length === 0) {
      container.innerHTML = '<div class="no-slots">Nav konsultāciju laiku.</div>';
      return;
    }

  
    const slotsByTeacher = {};
    data.forEach(slot => {
      const key = slot.teacher_name;
      if (!slotsByTeacher[key]) {
        slotsByTeacher[key] = [];
      }
      slotsByTeacher[key].push(slot);
    });

    container.innerHTML = "";
    Object.keys(slotsByTeacher).sort().forEach(teacherName => {
      const teacherSection = document.createElement("div");
      teacherSection.className = "teacher-slots-section";
      teacherSection.innerHTML = `<h4 class="teacher-name-header">${teacherName}</h4>`;
      
      const slotsGrid = document.createElement("div");
      slotsGrid.className = "slots-grid";

      slotsByTeacher[teacherName].forEach(slot => {
        const div = document.createElement("div");
        div.className = "slot-card";
        div.innerHTML = `
          <div class="slot-info">
            <div><strong>${slot.day}</strong></div>
            <div>${slot.time}</div>
            <div>🏢 ${slot.room}</div>
            <div> ${slot.date}</div>
            <div class="slot-capacity">${slot.current_requests}/${slot.max_students} skolēni</div>
          </div>
          <div class="slot-actions">
            <button onclick="deleteSlot(${slot.id}, ${slot.current_requests})" class="btn-delete">🗑️ Dzēst</button>
          </div>
        `;
        slotsGrid.appendChild(div);
      });

      teacherSection.appendChild(slotsGrid);
      container.appendChild(teacherSection);
    });
  } catch (error) {
    console.error("Error loading slots:", error);
    container.innerHTML = '<div class="error">Kļūda ielādējot konsultācijas.</div>';
  }
}

async function deleteSlot(slotId, currentRequests) {
  if (currentRequests > 0) {
    if (!confirm(`Šim laikam ir ${currentRequests} pieteikumi. Dzēst slotu kopā ar pieteikumiem?`)) return;
  } else {
    if (!confirm("Vai tiešām vēlaties dzēst šo slotu?")) return;
  }

  try {
    const res = await fetch("/api/admin/delete-slot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: slotId })
    });

    const data = await res.json();
    if (!res.ok) {
      showAdminMessage(data.error || "Kļūda dzēšot slotu", "error");
      return;
    }

    showAdminMessage("Slots veiksmīgi dzēsts", "success");
    loadAdminSlots();
    loadStats();
  } catch (error) {
    console.error("Error deleting slot:", error);
    showAdminMessage("Kļūda dzēšot slotu", "error");
  }
}

async function loadUsers() {
  const container = document.getElementById("users-list");
  if (!container) return;

  try {
    const res = await fetch("/api/admin/users");
    if (!res.ok) {
      throw new Error("Kļūda ielādējot lietotājus");
    }
    const data = await res.json();

    const roleFilter = document.getElementById("user-role-filter")?.value || "";
    const filtered = roleFilter ? data.filter(u => u.role === roleFilter) : data;

    if (filtered.length === 0) {
      container.innerHTML = '<div class="no-requests">Nav lietotāju ar izvēlēto filtru.</div>';
      return;
    }

    container.innerHTML = "";
    
    // Grupēšana pēc lomas
    const usersByRole = {};
    filtered.forEach(user => {
      if (!usersByRole[user.role]) {
        usersByRole[user.role] = [];
      }
      usersByRole[user.role].push(user);
    });

    Object.keys(usersByRole).sort().forEach(role => {
      const roleSection = document.createElement("div");
      const roleLabel = role === "student" ? "Skolēni" : role === "teacher" ? "Skolotāji" : "Administratori";
      roleSection.innerHTML = `<h4 class="role-header">${roleLabel} (${usersByRole[role].length})</h4>`;
      
      const usersGrid = document.createElement("div");
      usersGrid.className = "users-grid";

      usersByRole[role].forEach(user => {
        const div = document.createElement("div");
        div.className = "user-card";
        
        let usernameDisplay = "";
        if (user.username) {
          usernameDisplay = `<div class="user-username">👤 ${user.username}</div>`;
        }

        div.innerHTML = `
          <div class="user-info">
            <div class="user-name"><strong>${user.name}</strong></div>
            ${usernameDisplay}
            <div class="user-role-badge role-${user.role}">${roleLabel}</div>
            ${user.email ? `<div class="user-email">📧 ${user.email}</div>` : ""}
          </div>
          <button onclick="deleteUser(${user.id}, '${user.name}')" class="btn-delete">🗑️ Dzēst</button>
        `;
        usersGrid.appendChild(div);
      });

      roleSection.appendChild(usersGrid);
      container.appendChild(roleSection);
    });
  } catch (error) {
    console.error("Error loading users:", error);
    container.innerHTML = '<div class="error">Kļūda ielādējot lietotājus.</div>';
  }
}

async function deleteUser(userId, userName) {
  if (!confirm(`Vai tiešām vēlaties dzēst lietotāju "${userName}"?`)) {
    return;
  }

  try {
    const res = await fetch("/api/admin/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: userId })
    });

    const data = await res.json();
    if (!res.ok) {
      showAdminMessage(data.error || "Kļūda dzēšot lietotāju", "error");
      return;
    }

    showAdminMessage("Lietotājs veiksmīgi dzēsts", "success");
    loadUsers();
    loadStats();
  } catch (error) {
    console.error("Error deleting user:", error);
    showAdminMessage("Kļūda dzēšot lietotāju", "error");
  }
}


// ADMIN – STATISTIKA 

async function loadStats() {
  try {
    const res = await fetch("/api/admin/stats");
    if (!res.ok) {
      throw new Error("Kļūda ielādējot statistiku");
    }
    const s = await res.json();

    document.getElementById("stat-students").textContent = s.students || 0;
    document.getElementById("stat-teachers").textContent = s.teachers || 0;
    document.getElementById("stat-slots").textContent = s.slots || 0;
    document.getElementById("stat-pending").textContent = s.pending || 0;
    document.getElementById("stat-accepted").textContent = s.accepted || 0;
    document.getElementById("stat-rejected").textContent = s.rejected || 0;
  } catch (error) {
    console.error("Error loading stats:", error);
  }
}

async function adminCleanup() {
  if (!confirm('Palaist automātisko tīrīšanu (dzēsīs beigušos pieteikumus)?')) return;
  try {
    const res = await fetch('/api/admin/cleanup', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      showAdminMessage(data.error || 'Kļūda tīrīšanā', 'error');
      return;
    }
    showAdminMessage(`Tīrīšana pabeigta. Dzēsti ${data.deleted_requests || 0} ieraksti.`, 'success');
    loadAdminSlots();
    loadStats();
  } catch (e) {
    console.error(e);
    showAdminMessage('Kļūda tīrīšanā', 'error');
  }
}


// AUTOMĀTISKĀ IELĀDE

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("calendar")) {
    loadSlots();
    loadStudentRequests();
  }
  if (document.getElementById("requests")) loadTeacherRequests();
  if (document.getElementById("slot-teacher")) {
    loadTeachersForAdmin();
    loadAdminSlots(); 
    loadUsers(); 
    loadStats(); 
  }
  if (document.getElementById("teacher-filter")) loadTeachersForStudent();
});
