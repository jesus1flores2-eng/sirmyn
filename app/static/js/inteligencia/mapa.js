/**
 * Mapa de Calor - Inteligencia Municipal
 * Interactividad para el mapa Leaflet
 */

class MapaInteligencia {
    constructor() {
        this.mapa = null;
        this.marcadores = [];
        this.capas = {};
        this.puntosActuales = [];
        this.initialize();
    }

    initialize() {
        this.setupEventListeners();
        this.inicializarMapa();
        this.cargarDatosMapa();
    }

    setupEventListeners() {
        // Botón para actualizar mapa
        document.getElementById('btnActualizarMapa')?.addEventListener('click', () => {
            this.cargarDatosMapa();
        });

        // Filtros
        document.getElementById('filtroTipoMapa')?.addEventListener('change', () => {
            this.cargarDatosMapa();
        });

        document.getElementById('filtroEstadoMapa')?.addEventListener('change', () => {
            this.cargarDatosMapa();
        });

        document.getElementById('filtroDiasMapa')?.addEventListener('change', () => {
            this.cargarDatosMapa();
        });

        // Controles de vista
        document.getElementById('btnSatelite')?.addEventListener('click', () => {
            this.cambiarVista('satellite');
        });

        document.getElementById('btnCalles')?.addEventListener('click', () => {
            this.cambiarVista('streets');
        });

        document.getElementById('btnLimpiar')?.addEventListener('click', () => {
            this.limpiarMapa();
        });
    }

    inicializarMapa() {
        // Crear mapa centrado en coordenadas aproximadas
        this.mapa = L.map('mapaCalor').setView(MAP_CONFIG.center, MAP_CONFIG.zoom);

        // Capa base de OpenStreetMap
        this.capas.calles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: MAP_CONFIG.maxZoom
        }).addTo(this.mapa);

        // Capa satélite (opcional)
        this.capas.satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: '© Esri',
            maxZoom: MAP_CONFIG.maxZoom
        });

        // Control de capas
        L.control.layers({
            'Calles': this.capas.calles,
            'Satélite': this.capas.satelite
        }).addTo(this.mapa);

        // Control de escala
        L.control.scale().addTo(this.mapa);

        // Evento para actualizar tabla cuando se mueve el mapa
        this.mapa.on('moveend', () => {
            this.actualizarTablaAreaVisible();
        });
    }

    async cargarDatosMapa() {
        try {
            const tipo = document.getElementById('filtroTipoMapa')?.value || '';
            const estado = document.getElementById('filtroEstadoMapa')?.value || '';
            const dias = document.getElementById('filtroDiasMapa')?.value || 30;

            const params = new URLSearchParams({
                dias: dias,
                ...(tipo && { tipo: tipo }),
                ...(estado && estado !== '' && { estado: estado })
            });

            console.log('📡 Solicitando datos de:', `${MAP_CONFIG.apiUrl}?${params}`);
            
            const response = await fetch(`${MAP_CONFIG.apiUrl}?${params}`);
            const data = await response.json();
            
            console.log('📦 Datos recibidos:', data);

            if (data.success) {
                this.puntosActuales = data.puntos || [];
                console.log(`📍 ${this.puntosActuales.length} puntos cargados`);
                
                this.renderizarMarcadores();
                
                // NUEVO: Ajustar vista automáticamente
                this.ajustarVistaAPuntos();
                
                this.actualizarEstadisticas();
                this.actualizarTablaAreaVisible();
            } else {
                console.error('❌ Error en la respuesta:', data.error);
                this.mostrarError(data.error || 'Error al cargar datos');
            }
        } catch (error) {
            console.error('🚨 Error cargando datos del mapa:', error);
            this.mostrarError(`Error de conexión: ${error.message}`);
        }
    }

    // NUEVO MÉTODO: Ajustar vista según los puntos
    ajustarVistaAPuntos() {
        if (this.puntosActuales.length === 0) {
            console.log('ℹ️ No hay puntos para ajustar vista');
            return;
        }

        // Si solo hay un punto, centrar en ese punto con zoom 15
        if (this.puntosActuales.length === 1) {
            const punto = this.puntosActuales[0];
            if (punto.coordenadas && punto.coordenadas.lat && punto.coordenadas.lng) {
                this.mapa.setView([punto.coordenadas.lat, punto.coordenadas.lng], 15);
                console.log(`🎯 Mapa centrado en: ${punto.coordenadas.lat}, ${punto.coordenadas.lng}`);
            }
        } else {
            // Si hay múltiples puntos, crear bounds
            const bounds = L.latLngBounds([]);
            this.puntosActuales.forEach(punto => {
                if (punto.coordenadas && punto.coordenadas.lat && punto.coordenadas.lng) {
                    bounds.extend([punto.coordenadas.lat, punto.coordenadas.lng]);
                }
            });
            
            if (bounds.isValid()) {
                this.mapa.fitBounds(bounds, { padding: [50, 50] });
            }
        }
    }

    renderizarMarcadores() {
        // Limpiar marcadores anteriores
        this.marcadores.forEach(marker => this.mapa.removeLayer(marker));
        this.marcadores = [];

        if (this.puntosActuales.length === 0) {
            console.log('ℹ️ No hay puntos para mostrar');
            return;
        }

        // Agrupar puntos por ubicación para identificar focos rojos
        const puntosAgrupados = this.agruparPuntosPorUbicacion();

        // Crear marcadores para focos rojos (múltiples reportes en misma ubicación)
        Object.entries(puntosAgrupados).forEach(([ubicacion, puntos]) => {
            if (puntos.length >= 5) {
                this.crearMarcadorFocoRojo(ubicacion, puntos);
            }
        });

        // Crear marcadores individuales
        this.puntosActuales.forEach(punto => {
            this.crearMarcadorIndividual(punto);
        });
    }

    agruparPuntosPorUbicacion() {
        const agrupados = {};
        
        this.puntosActuales.forEach(punto => {
            if (punto.coordenadas && punto.coordenadas.lat && punto.coordenadas.lng) {
                const clave = `${punto.coordenadas.lat.toFixed(4)},${punto.coordenadas.lng.toFixed(4)}`;
                if (!agrupados[clave]) {
                    agrupados[clave] = [];
                }
                agrupados[clave].push(punto);
            }
        });
        
        return agrupados;
    }

    crearMarcadorIndividual(punto) {
        // Verificar que tenga coordenadas válidas
        if (!punto.coordenadas || !punto.coordenadas.lat || !punto.coordenadas.lng) {
            console.warn('Punto sin coordenadas válidas:', punto);
            return;
        }

        // Determinar color según estado
        const color = punto.estado === 'Atendido' ? 'green' : 'red';
        const icono = punto.estado === 'Atendido' ? 'check-circle' : 'exclamation-circle';

        // Crear marcador
        const marker = L.marker([punto.coordenadas.lat, punto.coordenadas.lng], {
            icon: L.divIcon({
                className: 'custom-marker',
                html: `
                    <div style="
                        background-color: ${color};
                        width: 20px;
                        height: 20px;
                        border-radius: 50%;
                        border: 2px solid white;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-size: 10px;
                    ">
                        <i class="fas fa-${icono}"></i>
                    </div>
                `,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            })
        });

        // Popup con información
        marker.bindPopup(`
            <div style="min-width: 250px;">
                <h6 class="mb-2">Reporte #${punto.id}</h6>
                <p><strong>Tipo:</strong> ${punto.tipo || 'N/A'}</p>
                <p><strong>Subtipo:</strong> ${punto.subtipo || 'N/A'}</p>
                <p><strong>Ubicación:</strong> ${punto.calle || 'N/A'}</p>
                <p><strong>Estado:</strong>
                    <span class="badge ${punto.estado === 'Atendido' ? 'bg-success' : 'bg-warning'}">
                        ${punto.estado || 'Desconocido'}
                    </span>
                </p>
                <hr>
                <button class="btn btn-sm btn-primary w-100"
                        onclick="mapa.verDetalleMarcador(${punto.id})">
                    <i class="fas fa-eye me-1"></i>Ver Detalles
                </button>
            </div>
        `);

        marker.addTo(this.mapa);
        this.marcadores.push(marker);
    }

    crearMarcadorFocoRojo(ubicacion, puntos) {
        const [lat, lng] = ubicacion.split(',').map(Number);
        const totalPuntos = puntos.length;

        // Determinar tamaño según cantidad
        const radio = Math.min(30, 15 + (totalPuntos * 2));

        const marker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'foco-rojo-marker',
                html: `
                    <div style="
                        background-color: ${totalPuntos >= 10 ? '#dc3545' : '#ffc107'};
                        width: ${radio}px;
                        height: ${radio}px;
                        border-radius: 50%;
                        border: 3px solid white;
                        box-shadow: 0 3px 10px rgba(0,0,0,0.4);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-weight: bold;
                        font-size: 12px;
                        cursor: pointer;
                    ">
                        ${totalPuntos}
                    </div>
                `,
                iconSize: [radio, radio],
                iconAnchor: [radio/2, radio/2]
            })
        });

        // Popup de foco rojo
        let popupContent = `<h6 class="mb-2">🚨 Foco Rojo</h6>`;
        popupContent += `<p><strong>Reportes pendientes:</strong> ${totalPuntos}</p>`;
        popupContent += `<p><strong>Tipos principales:</strong><br>`;
        
        // Agrupar por tipo
        const tipos = {};
        puntos.forEach(p => {
            tipos[p.tipo] = (tipos[p.tipo] || 0) + 1;
        });
        
        Object.entries(tipos).forEach(([tipo, cantidad]) => {
            popupContent += `• ${tipo}: ${cantidad} reportes<br>`;
        });
        
        popupContent += `</p>`;
        popupContent += `<button class="btn btn-sm btn-danger w-100 mt-2"
                            onclick="mapa.verDetalleFoco('${puntos[0].localidad || ''}', '${puntos[0].tipo || ''}')">
                            <i class="fas fa-fire me-1"></i>Ver Reportes
                        </button>`;

        marker.bindPopup(popupContent);
        marker.addTo(this.mapa);
        this.marcadores.push(marker);
    }

    actualizarEstadisticas() {
        // Contar puntos
        document.getElementById('contadorPuntos').textContent = this.puntosActuales.length;

        // Contar focos rojos (5+ reportes en misma ubicación)
        const agrupados = this.agruparPuntosPorUbicacion();
        const focosRojos = Object.values(agrupados).filter(puntos => puntos.length >= 5).length;
        document.getElementById('contadorFocos').textContent = focosRojos;

        // Tipo predominante
        const tipos = {};
        this.puntosActuales.forEach(p => {
            tipos[p.tipo] = (tipos[p.tipo] || 0) + 1;
        });
        
        if (Object.keys(tipos).length > 0) {
            const tipoPred = Object.entries(tipos).sort((a, b) => b[1] - a[1])[0];
            document.getElementById('tipoPredominante').textContent = `${tipoPred[0] || 'Desconocido'} (${tipoPred[1]})`;
        } else {
            document.getElementById('tipoPredominante').textContent = '-';
        }
    }

    actualizarTablaAreaVisible() {
        if (!this.mapa || this.puntosActuales.length === 0) {
            const tbody = document.getElementById('cuerpoTablaMapa');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center text-muted">
                            No hay reportes para mostrar
                        </td>
                    </tr>
                `;
            }
            return;
        }

        const bounds = this.mapa.getBounds();
        const tbody = document.getElementById('cuerpoTablaMapa');
        
        if (!tbody) return;

        // Filtrar puntos dentro del área visible
        const puntosVisibles = this.puntosActuales.filter(punto => {
            if (!punto.coordenadas || !punto.coordenadas.lat || !punto.coordenadas.lng) {
                return false;
            }
            const latLng = L.latLng(punto.coordenadas.lat, punto.coordenadas.lng);
            return bounds.contains(latLng);
        }).slice(0, 10); // Limitar a 10 puntos

        if (puntosVisibles.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted">
                        No hay reportes en el área visible del mapa
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        puntosVisibles.forEach(punto => {
            html += `
                <tr>
                    <td>#${punto.id}</td>
                    <td>
                        <span class="badge bg-primary">${punto.tipo || 'N/A'}</span>
                    </td>
                    <td>
                        <small>${punto.localidad || ''}<br>
                        ${punto.calle || ''}</small>
                    </td>
                    <td>
                        <span class="badge ${punto.estado === 'Atendido' ? 'bg-success' : 'bg-warning'}">
                            ${punto.estado || 'Desconocido'}
                        </span>
                    </td>
                    <td>
                        <small>${punto.fecha || new Date().toLocaleDateString()}</small>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary"
                                onclick="mapa.verDetalleMarcador(${punto.id})">
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    }

    verDetalleMarcador(id) {
        const punto = this.puntosActuales.find(p => p.id === id);
        if (!punto) {
            this.mostrarError('No se encontró el reporte');
            return;
        }

        const modalBody = document.getElementById('cuerpoModalDetalle');
        const btnVerCompleto = document.getElementById('btnVerReporteCompleto');

        modalBody.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6>Información del Reporte</h6>
                    <p><strong>ID:</strong> #${punto.id}</p>
                    <p><strong>Tipo:</strong> ${punto.tipo || 'N/A'}</p>
                    <p><strong>Subtipo:</strong> ${punto.subtipo || 'N/A'}</p>
                    <p><strong>Estado:</strong>
                        <span class="badge ${punto.estado === 'Atendido' ? 'bg-success' : 'bg-warning'}">
                            ${punto.estado || 'Desconocido'}
                        </span>
                    </p>
                </div>
                <div class="col-md-6">
                    <h6>Ubicación</h6>
                    <p>${punto.localidad || 'N/A'}</p>
                    <p>${punto.calle || 'N/A'}</p>
                    <h6 class="mt-3">Coordenadas</h6>
                    <p>${punto.coordenadas ? `${punto.coordenadas.lat.toFixed(6)}, ${punto.coordenadas.lng.toFixed(6)}` : 'No disponibles'}</p>
                </div>
            </div>
        `;

        btnVerCompleto.href = `/admin/historial?reporte_id=${punto.id}`;

        const modal = new bootstrap.Modal(document.getElementById('modalDetalleMarcador'));
        modal.show();
    }

    verDetalleFoco(localidad, tipo) {
        // Redirigir a reportes detallados con filtros
        const url = `/inteligencia/reporte-detallado?localidad=${encodeURIComponent(localidad)}&tipo=${encodeURIComponent(tipo)}`;
        window.open(url, '_blank');
    }

    cambiarVista(tipo) {
        if (tipo === 'satellite') {
            this.mapa.removeLayer(this.capas.calles);
            this.capas.satelite.addTo(this.mapa);
        } else {
            this.mapa.removeLayer(this.capas.satelite);
            this.capas.calles.addTo(this.mapa);
        }
    }

    limpiarMapa() {
        this.marcadores.forEach(marker => this.mapa.removeLayer(marker));
        this.marcadores = [];
        this.puntosActuales = [];
        
        document.getElementById('contadorPuntos').textContent = '0';
        document.getElementById('contadorFocos').textContent = '0';
        document.getElementById('tipoPredominante').textContent = '-';
        
        const tbody = document.getElementById('cuerpoTablaMapa');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted">
                        Mapa limpiado - Aplica filtros para cargar datos
                    </td>
                </tr>
            `;
        }
    }

    mostrarError(mensaje) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show position-fixed top-0 end-0 m-3';
        alert.style.zIndex = '9999';
        alert.innerHTML = `
            <strong>Error en el mapa:</strong> ${mensaje}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(alert);
        
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }
}

// Inicializar mapa cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    window.mapa = new MapaInteligencia();
});