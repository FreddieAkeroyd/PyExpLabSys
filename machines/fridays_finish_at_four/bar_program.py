#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Barcode scanner module"""

import sys
import os
import time
import subprocess
from bar_database import *
from PyExpLabSys.drivers.four_d_systems import PicasouLCD28PTU, to_ascii
from serial.serialutil import SerialException
from PyExpLabSys.drivers.vivo_technologies import ThreadedLS689A, detect_barcode_device
from ssh_tunnel import create_tunnel, close_tunnel, get_ip_address, test_demon_connection


__version__ = 1.000
#bar_database = BarDatabase()
#bar_database = None


def cowsay(text):
    """Display text in Cowsay manner"""
    p = subprocess.Popen(["/usr/games/cowsay", "-W34", str(text)], stdout=subprocess.PIPE)
    out, err = p.communicate()
    return out


class NewBarcode(Exception):
    """Custom exception used to signal that a new barcode has been received"""
    def __init__(self, barcode):
        self.barcode = barcode
        super(NewBarcode, self).__init__()


class Bar101(object):
    """Barcodescanner programme class """
    def __init__(self):
        #Initialize internal variables
        self.tbs = None
        self.bar_database = None
        #Setup of display
        for port in range(8):
            try:
                device = '/dev/ttyUSB{}'.format(port)
                picaso = PicasouLCD28PTU(serial_device=device, baudrate=9600)
                spe_version = picaso.get_spe_version()
                picaso.screen_mode('landscape reverse')
                if spe_version == '1.2':
                    self.picaso = picaso
                    break
            except SerialException:
                pass


    def timer(self, timeout=3):
        """Set timeout to None to run forever"""
        while timeout is None or timeout > 0:
            time.sleep(0.1)
            if timeout is not None:
                timeout -= 0.1
            barcode = self.tbs.last_barcode_in_queue
            if barcode is not None:
                raise NewBarcode(barcode)

    def start_up(self):
        """Starting up initials"""
        self.picaso.clear_screen()

        #testing demon connection
        attempt_number = 0
        while not test_demon_connection():
            self.picaso.move_cursor(2, 0)
            attempt_number += 1
            status_string = "Demon connection attempt {} failed".format(attempt_number)
            self.picaso.put_string(status_string)
            time.sleep(1)
        self.picaso.clear_screen()
        self.picaso.move_cursor(2, 0)
        status_string = "Demon connection attempt succeeded".format(attempt_number)
        self.picaso.put_string(status_string)

        # Print network interface and ip address
        interface, ip_address = get_ip_address()
        self.picaso.move_cursor(5, 0)
        interface_string = "Interface: {}".format(interface)
        self.picaso.put_string(interface_string)
        self.picaso.move_cursor(6, 0)
        ip_address_string = "Ip address: {}".format(ip_address)
        self.picaso.put_string(ip_address_string)

        # Start the database backend
        self.bar_database = BarDatabase()

        #Start barcode scanner
        dev_ = detect_barcode_device()
        print dev_
        self.tbs = ThreadedLS689A(dev_)
        self.tbs.start()
        time.sleep(2)

    def clean_up(self):
        """Closing down"""
        self.tbs.close()
        print 'cleaning up'
        time.sleep(1)

    def query_barcode(self):
        """Initial message"""
        self.picaso.clear_screen()
        self.picaso.move_cursor(1,0)
        self.picaso.put_string(cowsay("Welcome to the Friday Bar. Please scan your barcode!"))
        self.picaso.move_cursor(19, 0)
        self.picaso.put_string("Friday Bar System Version {}".format(__version__))
        self.timer(None)

    def present_beer(self, barcode):
        # INSERT Show beer
        import time
        self.picaso.clear_screen()
        t0 = time.time()
        beer_price = str(self.bar_database.get_item(barcode, statement='price'))
        print "database", time.time() - t0
        cowsay_string = cowsay("Special price for you my friend: " + beer_price + " DKK")
        print "cowsay", time.time() - t0
        self.picaso.move_cursor(4, 4)
        self.picaso.put_string("Special price for you my friend:")
        self.picaso.move_cursor(7, 5)
        self.picaso.text_factor(5)
        self.picaso.put_string(beer_price + " DKK")
        print "put string", time.time() - t0

        self.timer(3)
        # INSERT Show spiffy comment
        self.picaso.clear_screen()
        self.picaso.move_cursor(1,0)
        self.picaso.put_string(cowsay("Enjoy your delicious " + str(self.bar_database.get_item(barcode, statement='name'))))
        self.timer(4)

    def present_insult(self):
        """Presents insult if programme handled wrong"""
        self.picaso.clear_screen()
        self.picaso.move_cursor(1,0)
        self.picaso.put_string(cowsay("You did it all wrong! Time to go home?"))
        self.timer(2)

    def purchase_beer(self, beer_barcode, user_barcode):
        """User purchases beer"""
        beer_price = self.bar_database.get_item(beer_barcode, statement='price')
        self.bar_database.insert_log(user_barcode, "purchase", beer_price)
        user_name = self.bar_database.get_user(user_barcode)
        beer_name = self.bar_database.get_item(beer_barcode, statement='name')

        self.picaso.clear_screen()
        self.picaso.move_cursor(1,0)
        self.picaso.put_string(cowsay("Welcome back " + user_name + ". Enjoy your " + beer_name + ". I will draw " + beer_price + " from your account."))
        self.timer(3)

    def make_deposit(self, user_barcode, amount):
        """User deposits money to user account"""
        pass

    def present_user(self, user_barcode):
        """Present user info, i.e. user name and balance"""
        user = self.bar_database.get_user(user_barcode)
        self.picaso.clear_screen()
        self.picaso.move_cursor(1,0)
        self.picaso.put_string(cowsay("Welcome (back)" + str(user) + "What can I serve for you today?"))
        self.timer(5)

    def run(self):
        """Main method"""
        # action is a reference to the method that will be called next, kwargs
        # is its arguments
        action = self.query_barcode
        kwargs = {}
        while True:
            try:
                # Call the pending action, if this action returns, the action
                # it was supposed to do, timed out, without getting a new
                # barcode and so we make the next action "query_barcode"
                action(**kwargs)
                old_action = action
                old_kwargs = kwargs
                # No new barcode recieved
                action = self.query_barcode
                kwargs = {}

            # We received a new barcode during the previous action
            except NewBarcode as new_barcode:
                old_action = action
                old_kwargs = kwargs
                barcode_type = self.bar_database.get_type(new_barcode.barcode)
                # Default to query_barcode
                action = self.query_barcode
                kwargs = {}
                if barcode_type == 'beer':
                    if old_action == self.present_user:
                        action = self.purchase_beer
                        kwargs = {'beer_barcode': new_barcode.barcode, 'user_barcode': old_kwargs['user_barcode']}
                    else:
                        action = self.present_beer
                        kwargs = {'barcode': new_barcode.barcode}
                elif barcode_type == 'user':
                    action = self.present_user
                    kwargs = {'user_barcode': new_barcode.barcode}
                    
                    
                    """
                    if old_action == self.present_beer:
                        #purchase beer
                        action = self.purchase_beer
                        kwargs = {}
                    elif old_action == self.query_barcode:
                        #present user info
                        action = self.present_user
                        kwargs = {}
                        """
                elif barcode_type == 'invalid':
                    action = self.present_insult
                    kwargs = {}


def main():
    """Main function"""
    bar101 = Bar101()
    while True:
        bar101.start_up()
        try:
            bar101.run()
        except KeyboardInterrupt:
            bar101.clean_up()
            bar101.picaso.close()
            break
        except:
            bar101.clean_up()
            raise

if __name__ == '__main__':
    main()