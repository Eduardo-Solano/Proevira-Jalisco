import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class InformacionScreen extends StatelessWidget {
  const InformacionScreen({super.key});

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            '¿Cómo usar Proevira?',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          const Text(
            'Consulta alertas epidemiológicas, registra tus síntomas y encuentra unidades médicas de Jalisco aunque estés fuera del estado.',
          ),
          const SizedBox(height: 16),
          const _InfoCard(
            icon: Icons.warning_amber,
            title: 'Alertas',
            text:
                'Recibe avisos activos de vigilancia epidemiológica. Desliza hacia abajo para actualizar.',
          ),
          const _InfoCard(
            icon: Icons.monitor_heart_outlined,
            title: 'Síntomas',
            text:
                'Registra tu evolución. Si no hay conexión, el reporte se guarda en el dispositivo y se sincroniza después.',
          ),
          const _InfoCard(
            icon: Icons.local_hospital_outlined,
            title: 'Unidades médicas',
            text:
                'Elige una zona de Jalisco para consultar CLUES cercanas. No necesitas encontrarte físicamente en esa zona.',
          ),
          Card(
            color: const Color(0xfffff1ef),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: const BorderSide(color: Color(0xfff3b4ad)),
            ),
            child: const Padding(
              padding: EdgeInsets.all(14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, color: Color(0xffb42318), size: 20),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Importante: esta aplicación es un asistente orientador y no sustituye el diagnóstico médico. Ante dificultad respiratoria, dolor intenso o empeoramiento, acude a urgencias.',
                      style: TextStyle(
                        color: Color(0xffb42318),
                        fontSize: 12,
                        height: 1.35,
                        decoration: TextDecoration.none,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: () async {
              final uri = Uri(scheme: 'tel', path: '911');
              if (await canLaunchUrl(uri)) await launchUrl(uri);
            },
            icon: const Icon(Icons.phone),
            label: const Text('Llamar al 911'),
          ),
        ],
      );
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.icon,
    required this.title,
    required this.text,
  });

  final IconData icon;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          contentPadding: const EdgeInsets.all(16),
          leading: Icon(icon, color: Theme.of(context).colorScheme.primary),
          title: Text(title),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(text),
          ),
        ),
      );
}
