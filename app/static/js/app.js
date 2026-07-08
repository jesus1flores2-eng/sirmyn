/**
 * Inicialización de DataTables con configuración avanzada
 * SOLO si DataTables está disponible Y la tabla exista
 */
$(document).ready(function() {
    // Verificar que DataTables esté cargado y la tabla exista
    if (typeof $.fn.DataTable !== 'undefined' && $('#reportsTable').length > 0) {
        try {
            $('#reportsTable').DataTable({
                language: {
                    url: '//cdn.datatables.net/plug-ins/1.13.6/i18n/es-ES.json'
                },
                responsive: true,
                dom: '<"top"lf>rt<"bottom"ip><"clear">',
                lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "Todos"]],
                pageLength: 25,
                order: [[1, 'desc']],
                stateSave: true,
                initComplete: function() {
                    $('.dataTables_length select').addClass('form-select form-select-sm');
                    $('.dataTables_filter input').addClass('form-control form-control-sm');
                    $('.dataTables_paginate .paginate_button').addClass('btn btn-sm');
                }
            });
        } catch (error) {
            console.warn('No se pudo inicializar DataTables:', error);
        }
    }
});

/**
 * Manejador de eventos cuando el DOM está completamente cargado
 */
document.addEventListener('DOMContentLoaded', function() {
    // Inicializar tooltips de Bootstrap
    initTooltips();
    
    // Configurar confirmación para acciones importantes
    setupActionConfirmation();
    
    // Mejorar experiencia en móviles
    enhanceMobileExperience();
    
    // Animaciones para filas de tabla
    animateTableRows();
    
    // Otros inicializadores
    initSidebarToggle();
    initDarkModeToggle();
});

/**
 * Inicializar todos los tooltips en la página
 */
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl, {
            trigger: 'hover focus',
            delay: { show: 300, hide: 100 }
        });
    });
}

/**
 * Configurar confirmación para acciones importantes
 */
function setupActionConfirmation() {
    const actionButtons = document.querySelectorAll('.btn-danger, .btn-warning, .btn-confirm');
    
    actionButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            const message = button.dataset.confirmMessage || '¿Estás seguro de realizar esta acción?';
            
            if (!confirm(message)) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
        });
    });
}

/**
 * Mejorar experiencia en dispositivos móviles
 */
function enhanceMobileExperience() {
    if (window.innerWidth < 768) {
        // Ajustar selects
        document.querySelectorAll('.form-select').forEach(select => {
            select.classList.add('form-select-sm');
        });
        
        // Ajustar inputs
        document.querySelectorAll('.form-control').forEach(input => {
            input.classList.add('form-control-sm');
        });
        
        // Ajustar botones
        document.querySelectorAll('.btn').forEach(btn => {
            btn.classList.add('btn-sm');
        });
    }
}

/**
 * Añadir animaciones a las filas de la tabla
 */
function animateTableRows() {
    // SOLO animar filas en tablas específicas (evitar tablas de gráficos)
    const tableRows = document.querySelectorAll('#reportsTable tbody tr, #tablaReportes tbody tr');
    
    tableRows.forEach((row, index) => {
        // Animación de entrada
        row.style.animationDelay = `${index * 0.03}s`;
        row.classList.add('animate__animated', 'animate__fadeIn');
        
        // Efecto hover
        row.addEventListener('mouseenter', () => {
            row.style.transform = 'translateX(2px)';
            row.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
            row.style.transition = 'all 0.2s ease';
        });
        
        row.addEventListener('mouseleave', () => {
            row.style.transform = '';
            row.style.boxShadow = '';
        });
    });
}

/**
 * Alternar sidebar (si existe)
 */
function initSidebarToggle() {
    const sidebarToggle = document.querySelector('#sidebarToggle');
    const sidebar = document.querySelector('#sidebar');
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            document.body.classList.toggle('sidebar-collapsed');
            
            // Guardar preferencia
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
        
        // Cargar estado inicial
        if (localStorage.getItem('sidebarCollapsed') === 'true') {
            sidebar.classList.add('collapsed');
            document.body.classList.add('sidebar-collapsed');
        }
    }
}

/**
 * Alternar modo oscuro
 */
function initDarkModeToggle() {
    const darkModeToggle = document.querySelector('#darkModeToggle');
    
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', () => {
            document.body.classList.toggle('dark-mode');
            
            // Guardar preferencia
            localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
        });
        
        // Cargar estado inicial
        if (localStorage.getItem('darkMode') === 'true') {
            document.body.classList.add('dark-mode');
        }
    }
}

/**
 * Manejar errores de AJAX globalmente
 */
$(document).ajaxError(function(event, jqxhr, settings, thrownError) {
    console.error("Error en la solicitud AJAX:", settings.url, thrownError);
    
    // Mostrar notificación al usuario
    const toastElement = document.getElementById('errorToast');
    if (toastElement) {
        const toast = new bootstrap.Toast(toastElement);
        document.getElementById('toastMessage').textContent =
            `Error al procesar la solicitud: ${thrownError || 'Error desconocido'}`;
        toast.show();
    }
});