import osgtest.library.core as core
import osgtest.library.osgunittest as osgunittest
import os
import re

class TestGratia(osgunittest.OSGTestCase):

    def test_01_gratia_admin_webpage (self):
         
        core.skip_ok_unless_installed('gratia-service')
        command = ('curl', 'http://fermicloud316.fnal.gov:8880/gratia-administration/status.html?wantDetails=0')
        status, stdout, stderr = core.system(command)
        #print "stdout is: " + str(stdout)
        #print "stderr is: " + str(stderr)
        self.assertEqual(status, 0, 'Unable to launch gratia admin webpage')
        
    def test_02_show_databases(self):
        core.skip_ok_unless_installed('gratia-service')    
       
        filename = "/tmp/gratia_admin_pass." + str(os.getpid()) + ".txt"
        #print filename
        f = open(filename,'w')
        f.write("[client]\n")
        f.write("password=admin\n")
        f.close()
        
        #Command to show the databases is:
        #echo "show databases;" | mysql --defaults-extra-file="/tmp/gratia_admin_pass.<pid>.txt" -B --unbuffered  --user=root --port=3306         
        command = "echo \"show databases;\" | mysql --defaults-extra-file=\"" + filename + "\" -B --unbuffered  --user=root --port=3306 | wc -l",
        status, stdout, stderr = core.system(command, shell=True)
        self.assertEqual(status, 0, 'Unable to install Gratia Database !')
        #self.assertEqual(stdout, 5, 'Incorrect total number of databases !')
        print "show_databases stdout is: " + stdout
        result = re.search('5', stdout, re.IGNORECASE)
        self.assert_(result is not None)
        os.remove(filename)
        
    def test_03_show_gratia_database_tables(self):
        core.skip_ok_unless_installed('gratia-service')    
       
        filename = "/tmp/gratia_admin_pass." + str(os.getpid()) + ".txt"
        #print filename
        f = open(filename,'w')
        f.write("[client]\n")
        f.write("password=admin\n")
        f.close()
        
        #Command to show the tabes in the gratia database is:
        #echo "use gratia;show tables;" | mysql --defaults-extra-file="/tmp/gratia_admin_pass.<pid>.txt" -B --unbuffered  --user=root --port=3306         
        command = "echo \"use gratia;show tables;\" | mysql --defaults-extra-file=\"" + filename + "\" -B --unbuffered  --user=root --port=3306 | wc -l",
        status, stdout, stderr = core.system(command, shell=True)
        self.assertEqual(status, 0, 'Unable to install Gratia Database !')
        #self.assertEqual(stdout, 5, 'Incorrect total number of databases !')
        print "show_gratia_database_tables stdout is: " + stdout
        result = re.search('82', stdout, re.IGNORECASE)
        self.assert_(result is not None)
        os.remove(filename)
        
        