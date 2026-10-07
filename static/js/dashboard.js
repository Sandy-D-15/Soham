function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");

    if (!sidebar) {
        return;
    }

    if (window.innerWidth <= 750) {
        sidebar.classList.toggle("mobile-open");
    } else {
        sidebar.classList.toggle("collapsed");
    }
}


function updateClock() {
    const currentDate = document.getElementById("currentDate");
    const currentTime = document.getElementById("currentTime");

    if (!currentDate || !currentTime) {
        return;
    }

    const now = new Date();

    const dateOptions = {
        day: "2-digit",
        month: "short",
        year: "numeric"
    };

    currentDate.innerText = now.toLocaleDateString(
        "en-IN",
        dateOptions
    );

    currentTime.innerText = now.toLocaleTimeString(
        "en-IN",
        {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        }
    );
}


document.addEventListener("DOMContentLoaded", function () {
    updateClock();

    setInterval(updateClock, 1000);
});