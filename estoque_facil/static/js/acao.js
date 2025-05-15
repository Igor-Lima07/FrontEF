document.addEventListener("DOMContentLoaded", function() {
    const delBtn = document.getElementById("delAcao");
    const editBtn = document.getElementById("editAcao");

    const toggleVisibility = (targetClass, otherClass) => {
        const targetBtns = document.getElementsByClassName(targetClass);
        const otherBtns = document.getElementsByClassName(otherClass);
        const isVisible = targetBtns.length > 0 && targetBtns[0].style.display === "flex";

        for (let btn of targetBtns) {
            btn.style.display = isVisible ? "none" : "flex";
        }
        for (let btn of otherBtns) {
            btn.style.display = "none";
        }
    };

    delBtn.addEventListener("click", function() {
        toggleVisibility("btnDelete", "btnEdit");
    });

    editBtn.addEventListener("click", function() {
        toggleVisibility("btnEdit", "btnDelete");
    });
});
