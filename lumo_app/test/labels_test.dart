import 'package:flutter_test/flutter_test.dart';
import 'package:lumo_app/lumo.dart';

void main() {
  test('minutes read like the iPhone timer', () {
    expect(minutesLabel(25), '25分');
    expect(minutesLabel(60), '1時間');
    expect(minutesLabel(90), '1時間30分');
    expect(minutesLabel(0), '0分');
  });

  test('shielding: extension running, could be installed, or impossible here', () {
    const mac =
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/142.0.0.0 Safari/537.36';
    const safari =
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) '
        'Version/26.0 Safari/605.1.15';
    const iphoneChrome =
        'Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 '
        '(KHTML, like Gecko) CriOS/142.0.0.0 Mobile/15E148 Safari/604.1';
    const android =
        'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/142.0.0.0 Mobile Safari/537.36';
    expect(shieldSupport(extension: true, computer: true, userAgent: mac), ShieldSupport.ready);
    expect(shieldSupport(extension: false, computer: true, userAgent: mac), ShieldSupport.needsExtension);
    expect(shieldSupport(extension: false, computer: true, userAgent: safari), ShieldSupport.unsupported);
    expect(shieldSupport(extension: false, computer: false, userAgent: iphoneChrome), ShieldSupport.unsupported);
    expect(shieldSupport(extension: false, computer: false, userAgent: android), ShieldSupport.unsupported);
  });
}
