/**
 * Dashboard de Inteligencia Municipal
 * Interactividad y gráficas
 */

class DashboardInteligencia {
    constructor() {
        this.charts = {};
        this.focosLimit = 10;
        this.initialize();
    }

    initialize() {
        this.setupEventListeners();
        this.cargarDatosIniciales();
        this.setupChartTemplates();
    }

    setupEventListeners() {
        // Filtros
        document.getElementById('filtrosForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.actualizarDashboard();
        });

        // Cargar más focos rojos
        document.getElementById('cargarMasFocos')?.addEventListener('click', () => {
            this.focosLimit += 10;
            this.cargarFocosRojos();
        });

        // Exportar gráfica
        document.getElementById('exportChart')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.exportarGrafica();
        });

        // Toggle data labels
        document.getElementById('toggleDataLabels')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleDataLabels();
        });
    }

    async cargarDatosIniciales() {
        try {
            await Promise.all([
                this.cargarEficienciaDepartamentos(),
                this.cargarFocosRojos(),
                this.cargarTendencias()
            ]);
        } catch (error) {
            console.error('Error cargando datos iniciales:', error);
            this.mostrarError('Error al cargar datos del dashboard');
        }
    }

    async cargarEficienciaDepartamentos() {
        try {
            const params = new URLSearchParams({
                dias: FLASK_VARS.filtros.dias,
                ...(FLASK_VARS.filtros.tipo && { tipo: FLASK_VARS.filtros.tipo }),
                ...(FLASK_VARS.filtros.localidad_id && { localidad_id: FLASK_VARS.filtros.localidad_id })
            });

            const response = await fetch(`${FLASK_VARS.urls.eficiencia}?${params}`);
            const data = await response.json();

            if (data.success) {
                this.actualizarMetricasRapidas(data);
                this.renderizarGraficaEficiencia(data);
                this.renderizarTablaDepartamentos(data);
            } else {
                throw new Error(data.error || 'Error en respuesta del servidor');
            }
        } catch (error) {
            console.error('Error cargando eficiencia:', error);
            this.mostrarError('Error al cargar datos de eficiencia');
        }
    }

    async cargarFocosRojos() {
        try {
            const params = new URLSearchParams({
                dias: FLASK_VARS.filtros.dias,
                limite: this.focosLimit,
                ...(FLASK_VARS.filtros.tipo && { tipo: FLASK_VARS.filtros.tipo })
            });

            const response = await fetch(`${FLASK_VARS.urls.focos_rojos}?${params}`);
            const data = await response.json();

            if (data.success) {
                this.renderizarFocosRojos(data.focos_rojos);
            }
        } catch (error) {
            console.error('Error cargando focos rojos:', error);
        }
    }

    async cargarTendencias() {
        try {
            const response = await fetch(FLASK_VARS.urls.tendencias);
            const data = await response.json();

            if (data.success) {
                this.renderizarGraficaTendencias(data.tendencias);
            }
        } catch (error) {
            console.error('Error cargando tendencias:', error);
        }
    }

    actualizarMetricasRapidas(data) {
        // Calcular totales
        const totalReportes = data.atendidos.reduce((a, b) => a + b, 0) + 
                             data.no_atendidos.reduce((a, b) => a + b, 0);
        const totalAtendidos = data.atendidos.reduce((a, b) => a + b, 0);
        const totalPendientes = data.no_atendidos.reduce((a, b) => a + b, 0);
        const eficienciaGeneral = totalReportes > 0 ? 
            Math.round((totalAtendidos / totalReportes) * 100) : 0;

        // Actualizar DOM
        document.getElementById('totalReportes').textContent = totalReportes.toLocaleString();
        document.getElementById('atendidos').textContent = totalAtendidos.toLocaleString();
        document.getElementById('pendientes').textContent = totalPendientes.toLocaleString();
        document.getElementById('eficienciaGeneral').textContent = `${eficienciaGeneral}%`;
    }

    renderizarGraficaEficiencia(data) {
        const ctx = document.getElementById('eficienciaChart');
        if (!ctx) return;

        // Destruir gráfica anterior si existe
        if (this.charts.eficiencia) {
            this.charts.eficiencia.destroy();
        }

        // Colores para las barras
        const backgroundColors = data.departamentos.map((_, index) => {
            const eficiencia = data.eficiencia[index];
            if (eficiencia >= 80) return 'rgba(75, 192, 192, 0.7)'; // Verde
            if (eficiencia >= 60) return 'rgba(255, 205, 86, 0.7)'; // Amarillo
            if (eficiencia >= 30) return 'rgba(255, 159, 64, 0.7)'; // Naranja
            return 'rgba(255, 99, 132, 0.7)'; // Rojo
        });

        this.charts.eficiencia = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.departamentos,
                datasets: [
                    {
                        label: 'Atendidos',
                        data: data.atendidos,
                        backgroundColor: 'rgba(54, 162, 235, 0.7)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    },
                    {
                        label: 'Pendientes',
                        data: data.no_atendidos,
                        backgroundColor: 'rgba(255, 99, 132, 0.7)',
                        borderColor: 'rgba(255, 99, 132, 1)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                label += context.parsed.y.toLocaleString();
                                
                                // Agregar porcentaje para el dataset
                                if (context.datasetIndex === 0) {
                                    const total = context.dataset.data[context.dataIndex] + 
                                                 context.chart.data.datasets[1].data[context.dataIndex];
                                    if (total > 0) {
                                        const porcentaje = Math.round((context.parsed.y / total) * 100);
                                        label += ` (${porcentaje}%)`;
                                    }
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 0
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value.toLocaleString();
                            }
                        }
                    }
                },
                onClick: (evt, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const departamento = data.departamentos[index];
                        this.verDetalleDepartamento(departamento);
                    }
                }
            }
        });
    }

    renderizarGraficaTendencias(tendencias) {
        const ctx = document.getElementById('tendenciasChart');
        if (!ctx) return;

        if (this.charts.tendencias) {
            this.charts.tendencias.destroy();
        }

        const meses = tendencias.map(t => t.mes);
        const totals = tendencias.map(t => t.total);
        const atendidos = tendencias.map(t => t.atendidos);

        this.charts.tendencias = new Chart(ctx, {
            type: 'line',
            data: {
                labels: meses,
                datasets: [
                    {
                        label: 'Total Reportes',
                        data: totals,
                        borderColor: 'rgba(54, 162, 235, 1)',
                        backgroundColor: 'rgba(54, 162, 235, 0.1)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: 'Atendidos',
                        data: atendidos,
                        borderColor: 'rgba(75, 192, 192, 1)',
                        backgroundColor: 'rgba(75, 192, 192, 0.1)',
                        tension: 0.1,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }

    renderizarFocosRojos(focos) {
        const tbody = document.getElementById('focosRojosBody');
        if (!tbody) return;

        // Actualizar contador
        document.getElementById('focosContador').textContent = 
            `${focos.length} focos rojos identificados`;

        if (focos.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted">
                        <i class="fas fa-check-circle text-success me-2"></i>
                        ¡Excelente! No se identificaron focos rojos con los filtros actuales.
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        focos.forEach((foco, index) => {
            // Determinar clase de gravedad
            let gravedadClass = '';
            let gravedadIcon = '';
            
            switch(foco.gravedad) {
                case 'critica':
                    gravedadClass = 'danger';
                    gravedadIcon = 'fa-fire';
                    break;
                case 'alta':
                    gravedadClass = 'warning';
                    gravedadIcon = 'fa-exclamation-triangle';
                    break;
                case 'media':
                    gravedadClass = 'info';
                    gravedadIcon = 'fa-exclamation-circle';
                    break;
                default:
                    gravedadClass = 'secondary';
                    gravedadIcon = 'fa-info-circle';
            }

            html += `
                <tr>
                    <td>
                        <strong>${foco.localidad}</strong><br>
                        <small class="text-muted">${foco.calle}</small>
                    </td>
                    <td>
                        <span class="badge bg-primary">${foco.tipo}</span>
                    </td>
                    <td>
                        <span class="badge bg-${gravedadClass} fs-6">
                            ${foco.reportes_pendientes}
                        </span>
                    </td>
                    <td>
                        <span class="badge bg-${gravedadClass}">
                            <i class="fas ${gravedadIcon} me-1"></i>
                            ${foco.gravedad.toUpperCase()}
                        </span>
                    </td>
                    <td>
                        <small>${foco.accion_sugerida}</small>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" 
                                onclick="dashboard.verDetalleFoco('${foco.localidad}', '${foco.tipo}')">
                            <i class="fas fa-search"></i>
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    }

    renderizarTablaDepartamentos(data) {
        const tbody = document.getElementById('departamentosBody');
        if (!tbody) return;

        let html = '';
        
        data.departamentos.forEach((depto, index) => {
            const atendidos = data.atendidos[index];
            const pendientes = data.no_atendidos[index];
            const total = atendidos + pendientes;
            const eficiencia = data.eficiencia[index];
            
            // Determinar estado
            let estadoClass = '';
            let estadoText = '';
            let estadoIcon = '';
            
            if (eficiencia >= 80) {
                estadoClass = 'success';
                estadoText = 'Excelente';
                estadoIcon = 'fa-check-circle';
            } else if (eficiencia >= 60) {
                estadoClass = 'info';
                estadoText = 'Bueno';
                estadoIcon = 'fa-thumbs-up';
            } else if (eficiencia >= 30) {
                estadoClass = 'warning';
                estadoText = 'Regular';
                estadoIcon = 'fa-exclamation-triangle';
            } else {
                estadoClass = 'danger';
                estadoText = 'Crítico';
                estadoIcon = 'fa-fire';
            }

            html += `
                <tr>
                    <td>
                        <strong>${depto}</strong>
                    </td>
                    <td>${total.toLocaleString()}</td>
                    <td>
                        <span class="text-success">${atendidos.toLocaleString()}</span>
                    </td>
                    <td>
                        <span class="text-danger">${pendientes.toLocaleString()}</span>
                    </td>
                    <td>
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar bg-${estadoClass}" 
                                 role="progressbar" 
                                 style="width: ${eficiencia}%"
                                 aria-valuenow="${eficiencia}" 
                                 aria-valuemin="0" 
                                 aria-valuemax="100">
                                ${eficiencia}%
                            </div>
                        </div>
                    </td>
                    <td>
                        <span class="badge bg-${estadoClass}">
                            <i class="fas ${estadoIcon} me-1"></i>
                            ${estadoText}
                        </span>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" 
                                onclick="dashboard.verDetalleDepartamento('${depto}')">
                            <i class="fas fa-chart-bar me-1"></i>Detalle
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    }

    async verDetalleDepartamento(departamento) {
        try {
            const url = FLASK_VARS.urls.detalle_departamento.replace('__TIPO__', encodeURIComponent(departamento));
            const response = await fetch(`${url}?dias=${FLASK_VARS.filtros.dias}`);
            const data = await response.json();
            
            if (data.success) {
                this.mostrarModalDetalle(data);
            }
        } catch (error) {
            console.error('Error cargando detalle:', error);
            this.mostrarError('Error al cargar detalle del departamento');
        }
    }

    mostrarModalDetalle(data) {
        // Crear contenido del modal
        let html = `
            <div class="modal fade" id="detalleModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-chart-bar me-2"></i>
                                Detalle: ${data.departamento}
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row mb-3">
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6>Subtipo de Problemas</h6>
                                            <ul class="list-group list-group-flush">
        `;

        // Subtipos
        data.detalle.subtipos.forEach(subtipo => {
            html += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    ${subtipo.nombre}
                    <span class="badge bg-primary rounded-pill">${subtipo.total}</span>
                </li>
            `;
        });

        html += `
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6>Calles Críticas</h6>
                                            <ul class="list-group list-group-flush">
        `;

        // Calles críticas
        data.detalle.calles_criticas.forEach(calle => {
            html += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    ${calle.calle}
                    <small class="text-muted">${calle.localidad}</small>
                    <span class="badge bg-danger rounded-pill">${calle.reportes_pendientes}</span>
                </li>
            `;
        });

        html += `
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="card">
                                <div class="card-body">
                                    <h6>Estadísticas</h6>
                                    <div class="row">
                                        <div class="col-md-4 text-center">
                                            <div class="display-6 text-primary">
                                                ${data.detalle.tiempo_promedio_atencion}h
                                            </div>
                                            <small class="text-muted">Tiempo promedio de atención</small>
                                        </div>
                                        <div class="col-md-8">
                                            <canvas id="detalleChart"></canvas>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cerrar</button>
                            <a href="${FLASK_VARS.urls.reporte_detallado}?tipo=${encodeURIComponent(data.departamento)}" 
                               class="btn btn-primary">
                                <i class="fas fa-external-link-alt me-1"></i>Ver Reportes
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Agregar modal al DOM
        const modalContainer = document.createElement('div');
        modalContainer.innerHTML = html;
        document.body.appendChild(modalContainer.firstElementChild);

        // Mostrar modal
        const modal = new bootstrap.Modal(document.getElementById('detalleModal'));
        modal.show();

        // Crear gráfica de detalle
        this.crearGraficaDetalle(data.detalle.total_por_mes);
    }

    crearGraficaDetalle(datos) {
        const ctx = document.getElementById('detalleChart');
        if (!ctx) return;

        const meses = datos.map(d => d.mes);
        const totals = datos.map(d => d.total);

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: meses,
                datasets: [{
                    label: 'Reportes por Mes',
                    data: totals,
                    backgroundColor: 'rgba(54, 162, 235, 0.7)'
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    verDetalleFoco(localidad, tipo) {
        // Redirigir a reportes detallados con filtros
        const params = new URLSearchParams({
            tipo: tipo,
            localidad: localidad,
            dias: FLASK_VARS.filtros.dias
        });
        
        window.location.href = `${FLASK_VARS.urls.reporte_detallado}?${params}`;
    }

    actualizarDashboard() {
        const form = document.getElementById('filtrosForm');
        const formData = new FormData(form);
        
        // Actualizar variables globales
        FLASK_VARS.filtros.dias = formData.get('dias');
        FLASK_VARS.filtros.tipo = formData.get('tipo');
        FLASK_VARS.filtros.localidad_id = formData.get('localidad_id');
        
        // Recargar datos
        this.cargarDatosIniciales();
    }

    exportarGrafica() {
        if (this.charts.eficiencia) {
            const link = document.createElement('a');
            link.download = `eficiencia-departamentos-${new Date().toISOString().slice(0,10)}.png`;
            link.href = this.charts.eficiencia.toBase64Image();
            link.click();
        }
    }

    toggleDataLabels() {
        // Implementar toggle de labels
        console.log('Toggle data labels');
    }

    setupChartTemplates() {
        // Configuración global de Chart.js
        Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
        Chart.defaults.color = '#6c757d';
        Chart.defaults.plugins.legend.labels.boxWidth = 12;
        Chart.defaults.plugins.legend.labels.padding = 20;
    }

    mostrarError(mensaje) {
        // Mostrar notificación de error
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show position-fixed top-0 end-0 m-3';
        alert.style.zIndex = '9999';
        alert.innerHTML = `
            <strong>Error:</strong> ${mensaje}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(alert);
        
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }
}

// Inicializar dashboard cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new DashboardInteligencia();
});