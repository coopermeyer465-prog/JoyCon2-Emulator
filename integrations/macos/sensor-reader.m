// Native CoreBluetooth input capture. No HID injection, pairing or flash commands.
// Protocol facts: ndeadly, JoeGeC/joycon2android and seitanmen/Joycon2forMac.
#import <Foundation/Foundation.h>
#import <CoreBluetooth/CoreBluetooth.h>
#import <fcntl.h>
#import <unistd.h>
#import <errno.h>

static NSString *const ServiceID = @"AB7DE9BE-89FE-49AD-828F-118F09DF7FD0";
static NSString *const InputID = @"AB7DE9BE-89FE-49AD-828F-118F09DF7FD2";
static NSString *const CommandID = @"649D4AC9-8EB7-4E6C-AF44-1EA54FE5F005";

static BOOL isSyncRight(NSData *data) {
    if (data.length < 26) return NO;
    const uint8_t *b = data.bytes;
    if (b[0] != 0x53 || b[1] != 0x05 || b[7] != 0x66 || b[8] != 0x20) return NO;
    for (NSUInteger i = 12; i < 18; i++) if (b[i] != 0) return NO;
    return YES;
}

static NSData *featureCommand(uint8_t subcommand) {
    const uint8_t bytes[] = {0x0C, 0x91, 1, subcommand, 0, 4, 0, 0, 0xFF, 0, 0, 0};
    return [NSData dataWithBytes:bytes length:sizeof(bytes)];
}

static NSDictionary *frame(NSData *data, NSTimeInterval elapsed) {
    if (data.length != 63) return nil;
    const uint8_t *bytes = data.bytes;
    NSMutableString *hex = [NSMutableString stringWithCapacity:126];
    for (NSUInteger i = 0; i < data.length; i++) [hex appendFormat:@"%02x", bytes[i]];
    return @{@"kind": @"common", @"elapsed": @(elapsed), @"data": hex};
}

static BOOL savePrivate(NSString *path, NSArray *frames, NSError **error) {
    NSData *json = [NSJSONSerialization dataWithJSONObject:@{@"version": @1, @"frames": frames}
                                                 options:0 error:error];
    if (!json) return NO;
    NSString *parent = path.stringByDeletingLastPathComponent;
    if (![[NSFileManager defaultManager] createDirectoryAtPath:parent withIntermediateDirectories:YES
                                                  attributes:@{NSFilePosixPermissions: @0700} error:error]) return NO;
    int fd = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
        return NO;
    }
    const uint8_t *bytes = json.bytes;
    NSUInteger sent = 0;
    while (sent < json.length) {
        ssize_t count = write(fd, bytes + sent, json.length - sent);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) {
            int code = count < 0 ? errno : EIO;
            close(fd);
            unlink(path.fileSystemRepresentation); // Only our newly created incomplete file.
            if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:code userInfo:nil];
            return NO;
        }
        sent += (NSUInteger)count;
    }
    if (close(fd) != 0) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
        return NO;
    }
    return YES;
}

@interface SensorReader : NSObject <CBCentralManagerDelegate, CBPeripheralDelegate>
@property (strong) CBCentralManager *central;
@property (strong) CBPeripheral *peripheral;
@property (strong) CBCharacteristic *command;
@property (strong) NSMutableDictionary<NSUUID *, CBPeripheral *> *candidates;
@property (strong) NSMutableArray *frames;
@property (strong) NSMutableDictionary<NSNumber *, NSNumber *> *lengths;
@property (copy) NSString *output;
@property NSTimeInterval seconds;
@property NSTimeInterval started;
@property BOOL scanStarted;
@property BOOL done;
@property int result;
- (void)start;
- (void)finish:(NSString *)failure;
@end

@implementation SensorReader
- (void)start {
    self.candidates = [NSMutableDictionary dictionary];
    self.frames = [NSMutableArray array];
    self.lengths = [NSMutableDictionary dictionary];
    self.result = 2;
    self.central = [[CBCentralManager alloc] initWithDelegate:self queue:dispatch_get_main_queue()
                                                    options:@{CBCentralManagerOptionShowPowerAlertKey: @NO}];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 45 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        [self finish:@"Reader timed out. Refresh SYNC; check Bluetooth permission if requested."];
    });
}
- (void)centralManagerDidUpdateState:(CBCentralManager *)central {
    if (self.done) return;
    if (central.state == CBManagerStateUnauthorized) {
        [self finish:@"Bluetooth access denied. Allow the helper in macOS Bluetooth privacy settings before retrying."];
    } else if (central.state == CBManagerStateUnsupported || central.state == CBManagerStatePoweredOff) {
        [self finish:@"Mac Bluetooth is unavailable or switched off. No settings were changed."];
    } else if (central.state == CBManagerStatePoweredOn && !self.scanStarted) {
        self.scanStarted = YES;
        puts("Scanning for one right Joy-Con 2 in SYNC mode; no pairing requested.");
        [central scanForPeripheralsWithServices:nil options:@{CBCentralManagerScanOptionAllowDuplicatesKey: @NO}];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (self.done) return;
            [central stopScan];
            if (self.candidates.count != 1) {
                [self finish:@"Expected exactly one right Joy-Con 2 in SYNC mode. Refresh SYNC and retry."];
                return;
            }
            self.peripheral = self.candidates.allValues.firstObject;
            self.peripheral.delegate = self;
            puts("Connecting through native CoreBluetooth.");
            [central connectPeripheral:self.peripheral options:nil];
        });
    }
}
- (void)centralManager:(CBCentralManager *)central didDiscoverPeripheral:(CBPeripheral *)peripheral
    advertisementData:(NSDictionary<NSString *, id> *)advertisementData RSSI:(NSNumber *)RSSI {
    NSData *manufacturer = advertisementData[CBAdvertisementDataManufacturerDataKey];
    if ([manufacturer isKindOfClass:NSData.class] && isSyncRight(manufacturer)) {
        self.candidates[peripheral.identifier] = peripheral;
    }
}
- (void)centralManager:(CBCentralManager *)central didConnectPeripheral:(CBPeripheral *)peripheral {
    puts("Connected; discovering common-input service.");
    [peripheral discoverServices:@[[CBUUID UUIDWithString:ServiceID]]];
}
- (void)centralManager:(CBCentralManager *)central didFailToConnectPeripheral:(CBPeripheral *)peripheral error:(NSError *)error {
    [self finish:@"Native BLE connection failed; no capture saved."];
}
- (void)centralManager:(CBCentralManager *)central didDisconnectPeripheral:(CBPeripheral *)peripheral error:(NSError *)error {
    if (!self.done) [self finish:@"Joy-Con disconnected before capture completed."];
}
- (void)peripheral:(CBPeripheral *)peripheral didDiscoverServices:(NSError *)error {
    CBService *inputService = nil;
    for (CBService *service in peripheral.services) {
        if ([service.UUID isEqual:[CBUUID UUIDWithString:ServiceID]]) inputService = service;
    }
    if (error || !inputService) {
        [self finish:@"Common-input service discovery failed."];
        return;
    }
    [peripheral discoverCharacteristics:@[[CBUUID UUIDWithString:InputID], [CBUUID UUIDWithString:CommandID]]
                             forService:inputService];
}
- (void)peripheral:(CBPeripheral *)peripheral didDiscoverCharacteristicsForService:(CBService *)service error:(NSError *)error {
    CBCharacteristic *input = nil;
    for (CBCharacteristic *characteristic in service.characteristics) {
        if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:InputID]]) input = characteristic;
        if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:CommandID]]) self.command = characteristic;
    }
    if (error || !input || !self.command || !(input.properties & CBCharacteristicPropertyNotify)
            || !(self.command.properties & CBCharacteristicPropertyWriteWithoutResponse)) {
        [self finish:@"Required input/command characteristics are unavailable."];
        return;
    }
    [peripheral setNotifyValue:YES forCharacteristic:input];
}
- (void)peripheral:(CBPeripheral *)peripheral didUpdateNotificationStateForCharacteristic:(CBCharacteristic *)characteristic error:(NSError *)error {
    if (self.done) return;
    if (error || !characteristic.isNotifying) {
        [self finish:@"Native input notification subscription failed."];
        return;
    }
    self.started = NSProcessInfo.processInfo.systemUptime;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 2), dispatch_get_main_queue(), ^{
        if (self.done) return;
        [peripheral writeValue:featureCommand(2) forCharacteristic:self.command type:CBCharacteristicWriteWithoutResponse];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 2), dispatch_get_main_queue(), ^{
            if (self.done) return;
            [peripheral writeValue:featureCommand(4) forCharacteristic:self.command type:CBCharacteristicWriteWithoutResponse];
            puts("Requested runtime reporting; recording briefly without calibration changes.");
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(self.seconds * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                [self finish:nil];
            });
        });
    });
}
- (void)peripheral:(CBPeripheral *)peripheral didUpdateValueForCharacteristic:(CBCharacteristic *)characteristic error:(NSError *)error {
    if (self.done || error || ![characteristic.UUID isEqual:[CBUUID UUIDWithString:InputID]]) return;
    NSData *data = characteristic.value;
    NSNumber *length = @(data.length);
    self.lengths[length] = @([self.lengths[length] unsignedIntegerValue] + 1);
    NSDictionary *sample = frame(data, NSProcessInfo.processInfo.systemUptime - self.started);
    if (sample && self.frames.count < 512) [self.frames addObject:sample];
    if (self.frames.count == 512) [self finish:nil];
}
- (void)finish:(NSString *)failure {
    if (self.done) return;
    self.done = YES;
    [self.central stopScan];
    if (self.peripheral.state == CBPeripheralStateConnected && self.command) {
        [self.peripheral writeValue:featureCommand(5) forCharacteristic:self.command type:CBCharacteristicWriteWithoutResponse];
    }
    if (!failure && self.frames.count) {
        NSError *error = nil;
        if (savePrivate(self.output, self.frames, &error)) {
            printf("Saved %lu native input reports privately.\n", (unsigned long)self.frames.count);
            self.result = 0;
        } else {
            fprintf(stderr, "Private capture could not be saved: %s\n", error.localizedDescription.UTF8String);
        }
    } else {
        fprintf(stderr, "%s\n", (failure ?: @"No native input reports received; no file written.").UTF8String);
        printf("Input notification lengths (no contents): %s\n", self.lengths.description.UTF8String);
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 4), dispatch_get_main_queue(), ^{
        if (self.peripheral) [self.central cancelPeripheralConnection:self.peripheral];
        CFRunLoopStop(CFRunLoopGetMain());
    });
}
@end

static int selfTest(void) {
    uint8_t adv[26] = {0x53, 0x05};
    adv[7] = 0x66; adv[8] = 0x20;
    if (!isSyncRight([NSData dataWithBytes:adv length:26])) return 1;
    adv[12] = 1;
    if (isSyncRight([NSData dataWithBytes:adv length:26]) || isSyncRight([NSData data])) return 1;
    if (featureCommand(2).length != 12 || frame([NSData data], 0)) return 1;
    if (!frame([NSMutableData dataWithLength:63], 0)) return 1;
    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSString *output = [directory stringByAppendingPathComponent:@"capture.json"];
    NSError *error = nil;
    if (!savePrivate(output, @[], &error) || savePrivate(output, @[], &error)) return 1;
    NSDictionary *attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:output error:nil];
    if (([attrs[NSFilePosixPermissions] unsignedIntValue] & 0777) != 0600) return 1;
    [[NSFileManager defaultManager] removeItemAtPath:directory error:nil];
    puts("Native self-tests passed: discovery filter, packet bounds, private/exclusive output.");
    return 0;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        setbuf(stdout, NULL);
        if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return selfTest();
        if (argc != 3) {
            fprintf(stderr, "Usage: mac-sensor-reader PRIVATE_OUTPUT SECONDS\n");
            return 2;
        }
        char *end = NULL;
        long seconds = strtol(argv[2], &end, 10);
        NSString *output = [NSString stringWithUTF8String:argv[1]];
        if (!output.isAbsolutePath || !end || *end || seconds < 1 || seconds > 15
                || [[NSFileManager defaultManager] fileExistsAtPath:output]) {
            fprintf(stderr, "Use a new absolute output path and 1..15 seconds.\n");
            return 2;
        }
        SensorReader *reader = [SensorReader new];
        reader.output = output;
        reader.seconds = seconds;
        puts("Native reader may request Bluetooth permission. It never requests pairing.");
        [reader start];
        CFRunLoopRun();
        return reader.result;
    }
}
