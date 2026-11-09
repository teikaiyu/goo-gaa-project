import 'package:flutter_test/flutter_test.dart';
import 'package:lumo_app/lumo.dart';

void main() {
  test('minutes read like the iPhone timer', () {
    expect(minutesLabel(25), '25分');
    expect(minutesLabel(60), '1時間');
    expect(minutesLabel(90), '1時間30分');
    expect(minutesLabel(0), '0分');
  });
}
