/* static/js/lab_effects.js - Efeitos estéticos para a Home Page do Lab */

document.addEventListener('DOMContentLoaded', function() {
    
    // --- 1. Efeito de Revelação no Scroll ---
    // Seleciona todas as secções com a classe .reveal-section
    const sections = document.querySelectorAll('.reveal-section');

    const observerOptions = {
        root: null, // usa a viewport do browser
        threshold: 0.15, // ativa quando 15% da secção está visível
        rootMargin: "0px"
    };

    const sectionObserver = new IntersectionObserver(function(entries, observer) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Adiciona a classe .active definida no CSS para iniciar a animação
                entry.target.classList.add('active');
                // Deixa de observar depois de revelar uma vez
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Começa a observar cada secção
    sections.forEach(section => {
        sectionObserver.observe(section);
    });

    // --- 2. Efeito de Digitação Automática (Hero) ---
    // Adaptado de bibliotecas comuns para ser minimalista
    var TxtType = function(el, toRotate, period) {
        this.toRotate = toRotate;
        this.el = el;
        this.loopNum = 0;
        this.period = parseInt(period, 10) || 2000;
        this.txt = '';
        this.tick();
        this.isDeleting = false;
    };

    TxtType.prototype.tick = function() {
        var i = this.loopNum % this.toRotate.length;
        var fullTxt = this.toRotate[i];

        if (this.isDeleting) {
            this.txt = fullTxt.substring(0, this.txt.length - 1);
        } else {
            this.txt = fullTxt.substring(0, this.txt.length + 1);
        }

        this.el.innerHTML = '<span class="wrap text-[#F39200]">'+this.txt+'</span>';

        var that = this;
        var delta = 150 - Math.random() * 100;

        if (this.isDeleting) { delta /= 2; }

        if (!this.isDeleting && this.txt === fullTxt) {
            delta = this.period;
            this.isDeleting = true;
        } else if (this.isDeleting && this.txt === '') {
            this.isDeleting = false;
            this.loopNum++;
            delta = 500;
        }

        setTimeout(function() {
            that.tick();
        }, delta);
    };

    var elements = document.getElementsByClassName('typewrite');
    for (var i=0; i<elements.length; i++) {
        var toRotate = elements[i].getAttribute('data-type');
        var period = elements[i].getAttribute('data-period');
        if (toRotate) {
          new TxtType(elements[i], JSON.parse(toRotate), period);
        }
    }
});