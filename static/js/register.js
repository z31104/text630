const spinWheel = document.getElementById("spinWheel");
const spinButton = document.getElementById("spinButton");
const lotteryResult = document.getElementById("lotteryResult");

const prizes = [
    "現折 50 元",
    "9 折券",
    "200元購物劵",
    "神秘小禮",
    "贈品三選一",
    "再接再厲"
];

let isSpinning = false;
let currentRotation = 0;

spinButton.addEventListener("click", function () {
    if (isSpinning) {
        return;
    }

    isSpinning = true;
    spinButton.disabled = true;
    lotteryResult.textContent = "抽獎中，請稍候...";

    spinWheel.style.setProperty("--wheel-text-fix", "0deg");

    const prizeIndex = Math.floor(Math.random() * prizes.length);
    const segmentDegree = 360 / prizes.length;

    const prizeCenterDegree = prizeIndex * segmentDegree + segmentDegree / 2;
    const targetDegree = 360 - prizeCenterDegree;

    const extraSpins = 5 * 360;
    const finalRotation = currentRotation + extraSpins + targetDegree;

    spinWheel.style.transform = `rotate(${finalRotation}deg)`;

    currentRotation = finalRotation;

    setTimeout(function () {
        spinWheel.style.setProperty("--wheel-text-fix", `${finalRotation}deg`);

        lotteryResult.textContent = `恭喜獲得：${prizes[prizeIndex]}`;
        spinButton.disabled = false;
        isSpinning = false;
    }, 4200);
});